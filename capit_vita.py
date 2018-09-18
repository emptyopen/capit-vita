###
# Takeezi
###

import urllib2
import json
import re
import os
import glob
import time
import pylab

import datetime as dt
import numpy as np
import pandas as pd

from operator import itemgetter
from math import sqrt

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from Robinhood import Robinhood

import smtplib
from os.path import basename
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate


'''
TO DO

update stocklist
look-back 3 years to see accuracy of RSI?
https://www.investopedia.com/articles/active-trading/011815/top-technical-indicators-rookie-traders.asp
auto sell architecture
'''


class CapitVita(object):

    def __init__(self, title = '', num_stocks = 15, mailing_list = [], debug = False):

        self.title = title
        self.num_stocks = num_stocks
        self.home_path = os.path.abspath(os.getcwd())
        if 'ec2-user' in self.home_path:
            self.home_path = '/home/ec2-user/capit-vita'
        self.file_path = self.home_path+'/data/'
        self.par_path = os.path.dirname(self.home_path) + '/'
        self.home_path = self.home_path + '/'
        if os.path.exists(self.par_path + '/takaomattcom/static/img/stocks/'):
            self.alt_file_path = self.par_path + '/takaomattcom/static/img/stocks/'
        else:
            self.alt_file_path = None
        #print('capit', self.home_path, self.file_path, self.par_path, self.alt_file_path)
        self.mailing_list = mailing_list
        self.debug = debug
        self.batchSize = 50

        with open(self.par_path + '/auth/alphavantage.txt') as f:
            self.av_API = f.read().split('\n')[0]

        with open(self.par_path + '/auth/robinhood.txt') as f:
            data = f.read().split('\n')
            robinhood_username = data[0]
            robinhood_password = data[1]
        self.trader = Robinhood()
        self.trader.login(username=robinhood_username, password=robinhood_password)


###########################################################################################################################################################
###      Find
###########################################################################################################################################################

    def find_stocks(self, graph = False):

        start_time = time.time()

        print('Initiating log...')
        ff = open(self.file_path+'readme.txt','w')
        ff.write(str(dt.datetime.now()))
        ff.write('\n')

        print('Deleting old files...')
        os.chdir(self.file_path)
        filelist = glob.glob('*.png')
        for f in filelist:
            os.remove(f)
        if self.alt_file_path != None:
            os.chdir(self.alt_file_path)
            filelist = glob.glob('*.png')
            for f in filelist:
                os.remove(f)
        os.chdir(self.home_path)

        print('Fetching stock list...')
        if os.path.isfile(self.home_path + 'options_stocklist.txt'):
            print('  Using weekly :)')
            with open(self.home_path+'options_stocklist.txt', 'r') as f:
                stockset = list(f.read().split(','))[:-2]
        else:
            print('  Using all :(')
            with open(self.home_path+'stocklist.txt', 'r') as f:
                stockset = list(f.read().split(','))
        if self.debug:
            stockset = stockset[:10]
        stockset_len = len(stockset)

        # for now, ignore the last 20 trade-attempted stocks
        ignore_these = [self.trader.get_url(x['instrument'])['symbol'] for x in self.trader.positions()['results'][-20:]]
        stockset = [x for x in stockset if x not in ignore_these]


        print('Grabbing data for {} stocks...'.format(stockset_len))
        stockPoints = {}
        for stock in stockset:
            try:
                points = self.get_points(stock)
                stockPoints[stock] = [sum([points[x] for x in points if x != 'trend']), points]
            #except BufferError:
            except Exception as e:
                print('failed {} because {}'.format(stock, e))
        lenOriginalStocks = len(stockPoints)

        print('Sorting stocks...')
        sortedStocks = sorted(stockPoints.items(), key=itemgetter(1), reverse = True)[:self.num_stocks]
        if graph:
            print('Graphing stocks...')
            for stock in [x[0] for x in sortedStocks]:
                try:
                    self.graph_data(stock, saveLocation = self.file_path)
                #except BufferError:
                except Exception as e:
                    print('failed {} because {}'.format(stock, e))

        print('Logging results...')
        ff.write('Cheap stocks to invest in for 2 days ~ 1 week: \n\n')
        ff.write('#\n')
        for i in sortedStocks:
            ff.write(i[0]+': '+str(round(i[1][0],1))+'  '+str(i[1][1])+'\n')
        ff.write('#\n')
        ff.write('\n\n  '+str(lenOriginalStocks)+' stocks filtered by point system to '+str(len(sortedStocks))+' stocks')
        ff.write("\n\n--- %s seconds ---" % (time.time() - start_time))
        ff.write('\n\n\n  Capit-Vita Version 4.4  (2018-06-10)\n\n')
        ff.close()

        print('Sending emails...')
        if len(self.mailing_list) > 0 and False:
            self.send_email(self.file_path, self.title+' Top '+str(self.num_stocks)+' Prospects', self.mailing_list)

        print('Done!')
        return sortedStocks


###########################################################################################################################################################
###      Grab
###########################################################################################################################################################


    def grab_data(self, signal_name, rng=140):

        try:

            tries = 0
            while True:
                url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={}&outputsize=full&apikey={}'.format(signal_name, self.av_API)
                request = urllib2.Request(url, headers={'User-Agent' : "Magic Browser"})
                temp = eval(urllib2.urlopen(request).read())
                if 'Time Series (Daily)' in temp:
                    break # exit if successful
                else:
                    time.sleep(1)
                    tries += 1
                if tries > 50: # in case we're trying too many calls?
                    break

            self.df = pd.DataFrame.from_dict(temp['Time Series (Daily)']).transpose()
            self.df = self.df.iloc[-rng:]
            self.df.columns = ['open', 'high', 'low', 'close', 'adjusted close', 'volume', 'dividend amount', 'split coefficient']
            self.df[['open','high','low','close','volume']] = self.df[['open','high','low','close','volume']].apply(pd.to_numeric)
            self.df['rsi'] = self.RSI(self.df['close'], 14)
            self.df['26 ema'] = self.df['close'].ewm(ignore_na=False,min_periods=0,adjust=True,com=26).mean()
            self.df['12 ema'] = self.df['close'].ewm(ignore_na=False,min_periods=0,adjust=True,com=12).mean()
            self.df['MACD'] = self.df['12 ema'] - self.df['26 ema']
            self.df['MACD trigger'] = self.df['MACD'].ewm(ignore_na=False,min_periods=0,adjust=True,com=9).mean()
            self.df['MACD signal'] = self.df['MACD'] - self.df['MACD'].ewm(ignore_na=False,min_periods=0,adjust=True,com=9).mean()
            self.df['MACD_norm'] = self.normalize(self.df['MACD signal'])
            self.df['MACD_der'] = self.derivative(self.df['MACD_norm'])

            self.sanitize_data()

        except BufferError:
        #except Exception as e:
            print('failed to get data because {}'.format(e))


    def sanitize_data(self):
        # this accounts for data sets where unaccounted splits are suspected

        self.df['split'] = self.df['close'] < (self.df.shift()['open'] * 0.65)
        m = self.df.pop('split').cumsum()
        self.df.loc[m.eq(1)] *= 2


    def generate_wiki_stocks(self):

        date = '20160912'

        #with open('rawStockList.txt', 'r') as f:
        #    data = json.load(f)

        url = 'https://www.quandl.com/api/v3/datatables/WIKI/PRICES.json?date='+date+'&api_key='+myAPI

        response = urllib2.urlopen(url)
        data = json.load(response)

        print(data)

        stocks = [str(x[0]) for x in data['datatable']['data']]

        with open('stockListAll.txt', 'wb') as f:
            for s in stocks:
                f.write(s)
                f.write(',')



###########################################################################################################################################################
###      Points
###########################################################################################################################################################

    def get_points(self, signal_name, criteria = {}):

        try:

            points = {}

            self.grab_data(signal_name)

            mb, tb, bb, = self.bbands(self.df['close'])
            if self.df['close'].iloc[-1] < (mb.iloc[-1] + bb.iloc[-1]) / 2:
                points['outside BB'] = -500

            if len(self.df['close']) < 100:
                points['too short'] = -500

            # RSI points (max 50)
            points['rsi'] = 50 - round(1.2 * abs(30-self.df['rsi'].iloc[-1]))

            # MACD points (max 40)
            macd_max = max(self.df['MACD'])
            macd_min = min(self.df['MACD'])
            macd_diff = macd_max - macd_min
            #print('max, min', macd_max, macd_min, macd_diff, self.df['MACD'].iloc[-1])
            #print('percentage', abs(self.df['MACD'].iloc[-1] / macd_diff))
            points['macd'] = round(40 * (1. - abs(self.df['MACD'].iloc[-1] / macd_diff)))
            #points['macd'] = round(30 * self.df['MACD_norm'].iloc[-1] / max([abs(x) for x in self.df['MACD_norm']]))
            #points['macd2'] = round(15 * self.df['MACD_der'].iloc[-1] / max([abs(x) for x in self.df['MACD_der']]))

            '''
            # candlestick points (max 10)
            #if style == 'option':
            candlestickFactor = 0
            patterns = self.detectCandlestickPatterns(self.df['open'][-7:],
                                self.df['close'][-7:], self.df['low'][-7:],
                                self.df['high'][-7:], candlestickFactor)
            points['candlesticks'] = self.rangeLimit(round(sum([x[2] for x in patterns])), -20, 20)
            '''

            # guru points (max 50)
            try:
                guru = self.get_guru(signal_name)
                points['guru_financial'] = 2.5*int(guru[0])
                points['guru_growth'] = 2.5*int(guru[1])
            except IndexError:
                print('failed Guru for {}'.format(signal_name))
                points['guru_financial'] = 15
                points['guru_growth'] = 15

            print(signal_name, points)

        except BufferError as e:
        #except Exception as e:
            print('failed getting points for {} because: {}'.format(signal_name, e))

        return points


    def get_guru(self, stock):
        fNp = []
        try:
            urlToVisit = 'http://www.gurufocus.com/stock/'+stock
            request = urllib2.Request(urlToVisit, headers={'User-Agent' : "Magic Browser"})
            sourceCode = urllib2.urlopen(request).read()
            finances = str(sourceCode).split(r'<a class="modally popup_window" href="#" id="rank_balancesheet">')
            profitability = str(sourceCode).split(r'<a href="#" class="modally popup_window" href="#" id="rank_profitability">')
            fNp.append(finances[1][1:].split('<')[0])
            fNp.append(profitability[1][1:].split('<')[0])
        #except Exception:
        except BufferError:
            fNp = [0,0]
        return fNp

    def detectCandlestickPatterns(self, openp,closep,lowp,highp,candlestickFactor=0.7):
        patterns = []
                 # candlestickFactor: higher value for higher impact
        engulfingStrength = 6
        tweezerStrength = 4
        dojiStrength = 3
        morningStarStrength = 6
        openp = list(openp)
        closep = list(closep)
        lowp = list(lowp)
        highp = list(highp)
        for i in range(len(openp)): # one candlestick patterns
            if abs(closep[i] - openp[i]) < 0.05 * (highp[i] - lowp[i]):
                if min([closep[i],openp[i]]) - lowp[i] > 2 * (highp[i] - max([closep[i],openp[i]])):
                    patterns.append(['dragonfly doji',i,dojiStrength*(sqrt(i+1)*candlestickFactor)])
                if min([closep[i],openp[i]]) - lowp[i] < 2 * (highp[i] - max([closep[i],openp[i]])):
                    patterns.append(['gravestone doji',i,-dojiStrength*(sqrt(i+1)*candlestickFactor)])
            if min([openp[i],closep[i]]) - lowp[i] <= 2 * abs(openp[i] - closep[i]) and \
                    highp[i] - max([openp[i],closep[i]]) <= 0.1 * abs(openp[i] - closep[i]) and \
                    max([openp[i],closep[i]]) - min([openp[i],closep[i]]) < min([closep[i],openp[i]]) - lowp[i]:
                patterns.append(['hammer',i,0*(sqrt(i+1)*candlestickFactor)])
        for i in range(1,len(openp)): # two candlestick patterns
            if closep[i] > openp[i-1] and openp[i] < closep[i-1] and openp[i-1] > closep[i-1]:
                patterns.append(['bullish engulfing',i,engulfingStrength*sqrt(i)*candlestickFactor])
            if closep[i] < openp[i-1] and openp[i] > closep[i-1] and openp[i-1] < closep[i-1]:
                patterns.append(['bearish engulfing',i,-engulfingStrength*sqrt(i)*candlestickFactor])
            if abs(openp[i]-closep[i-1]) < 0.05 * (highp[i] - lowp[i] + highp[i-1] - lowp[i-1])/2 and \
                    abs(closep[i]-openp[i-1]) < 0.1 * (highp[i] - lowp[i] + highp[i-1] - lowp[i-1])/2 and \
                    openp[i] < closep[i]:
                patterns.append(['tweezer bottoms',i,tweezerStrength*sqrt(i)*candlestickFactor])
            if abs(openp[i]-closep[i-1]) < 0.05 * (highp[i] - lowp[i] + highp[i-1] - lowp[i-1])/2 and \
                    abs(closep[i]-openp[i-1]) < 0.1 * (highp[i] - lowp[i] + highp[i-1] - lowp[i-1])/2 and \
                    openp[i] > closep[i]:
                patterns.append(['tweezer tops',i,-tweezerStrength*sqrt(i)*candlestickFactor])
        for i in range(2,len(openp)): # three candlestick patterns
            if openp[i-2] > closep[i-2] and openp[i] < closep[i] and \
                    max([closep[i-1],openp[i-1]]) < min([closep[i-2],openp[i]]) and \
                    abs(closep[i-1] - openp[i-1]) < 0.4 * (abs(closep[i-2] - openp[i-2])+abs(closep[i] - openp[i])) / 2:
                patterns.append(['morning star',i,morningStarStrength*(sqrt(i-1)*candlestickFactor)])
        return patterns

###########################################################################################################################################################
###      Graphing
###########################################################################################################################################################

    def graph_data(self, signal_name, rng = 100, saveLocation = ''):

        try:

            # create signals
            #self.grab_data(signal_name, rng)
            points = self.get_points(signal_name) # this grabs the data as well

            # grab data
            if 'time' in self.df:  ## from crypto
                date = self.df['date']
                volume = self.df['volumeto']
            else: ## regular
                date = pd.Series(self.df.index)
                volume = self.df['volume']

            openp = self.df['open']
            closep = self.df['close']
            highp = self.df['high']
            lowp = self.df['low']
            date = date.apply(lambda x: mdates.date2num(dt.datetime.strptime(x, '%Y-%m-%d')))

            mb, tb, bb, = self.bbands(closep)

            datemin = date.min() + 30
            datemax = date.max() + 45

            # make colors
            good_color = '#53C156'
            bad_color = '#ff1717'
            blue_color = '#3fcaff'
            spine_color = '#808080'
            label_color = 'k'

            rowNum = 20
            colNum = 4

            # identify fig
            plt.figure(facecolor='w',figsize=(18.,11.))
            plt.suptitle(signal_name,color=label_color, size='xx-large')
            plt.subplots_adjust(left=.125,bottom=.01,right=.9,top=.92,wspace=.2,hspace=0.1)

            # plot rsi ---------------------------------------------------------------------------------------
            ax_rsi = plt.subplot2grid((rowNum,colNum),(0,0),rowspan=3,colspan=4)
            plt.ylabel('RSI',color=label_color)
            ax_rsi.yaxis.tick_right()
            ax_rsi.grid(True,color=spine_color)
            ax_rsi.yaxis.label.set_color(spine_color)
            ax_rsi.spines['bottom'].set_color(spine_color)
            ax_rsi.spines['top'].set_color(spine_color)
            ax_rsi.spines['left'].set_color(spine_color)
            ax_rsi.spines['right'].set_color(spine_color)
            ax_rsi.tick_params(axis='y',colors=spine_color)
            ax_rsi.set_yticks([30,70])
            ax_rsi.axhline(70,color = bad_color)
            ax_rsi.axhline(30,color = good_color)
            plt.setp(ax_rsi.get_xticklabels(),visible=False)

            # plot RSI
            ax_rsi.plot(date, self.df['rsi'], color='k', linewidth=2, alpha=0.5)
            pylab.ylim([0,100])


            # main plot ---------------------------------------------------------------------------------------
            ax_main = plt.subplot2grid((rowNum,colNum),(3,0),rowspan=8,colspan=4,sharex=ax_rsi)
            plt.ylabel('Price and Volume',color=label_color)
            ax_main.grid(True,color=spine_color, which='major')
            ax_main.grid(True,color=spine_color, which='minor', alpha=0.7)
            ax_main.xaxis.set_major_locator(mticker.MaxNLocator(10))
            ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax_main.yaxis.label.set_color(spine_color)
            ax_main.spines['bottom'].set_color(spine_color)
            ax_main.spines['top'].set_color(spine_color)
            ax_main.spines['left'].set_color(spine_color)
            ax_main.spines['right'].set_color(spine_color)
            ax_main.tick_params(axis='y',colors=spine_color)
            ax_main.yaxis.set_major_locator(mticker.MaxNLocator(prune='both'))
            plt.setp(ax_main.get_xticklabels(),visible=False)

            # plot Bollinger bands
            ax_main.plot(date,tb,'#adbdd6',alpha=0.9,label='TB')
            ax_main.plot(date,bb,'#adbdd6',alpha=0.9,label='BB')
            ax_main.plot(date,mb,'#ba970d',alpha=0.7,label='MA')

            # min max stuff
            min1, min2 = self.finalMinIndex(lowp)
            max_main, max_macd = self.finalMaxIndex(highp)
            d1 = int((min1+max_main)/2)
            d2 = int((min2+max_macd)/2)
            ax_main.plot([date[d1],date[d2]],[closep[d1],closep[d2]],linewidth=8,color=blue_color,alpha=0.8,linestyle=':')

            # plot candlestick
            candleAr = [[date[x],openp[x],closep[x],highp[x],lowp[x]] for x in range(len(date))]
            self.candlestick(ax_main, candleAr, width = 0.5, colorup = good_color, colordown = bad_color)
            #ax_main.yaxis.tick_right()
            ax_main.yaxis.set_ticks_position('both')

            ''' commented out because it moves the axis ticks
            # plot volume
            ax_main_v = ax_main.twinx()
            ax_main_v.grid(False)
            ax_main_v.axes.yaxis.set_ticklabels([])
            ax_main_v.spines['bottom'].set_color(spine_color)
            ax_main_v.spines['top'].set_color(spine_color)
            ax_main_v.spines['left'].set_color(spine_color)
            ax_main_v.spines['right'].set_color(spine_color)
            ax_main_v.yaxis.label.set_color(spine_color)
            ax_main_v.xaxis.label.set_color(spine_color)
            ax_main_v.fill_between(date,0,volume,facecolor='#8e8e87',alpha=.1)
            '''


            # plot MACD ---------------------------------------------------------------------------------------
            ax_macd = plt.subplot2grid((rowNum,colNum),(11,0),rowspan=3,colspan=4,sharex=ax_rsi)
            plt.ylabel('MACD',color=label_color)
            #ax_macd.yaxis.tick_right()
            ax_macd.grid(True,color=spine_color, which='both')
            ax_macd.yaxis.label.set_color(spine_color)
            ax_macd.spines['bottom'].set_color(spine_color)
            ax_macd.spines['top'].set_color(spine_color)
            ax_macd.spines['left'].set_color(spine_color)
            ax_macd.spines['right'].set_color(spine_color)
            ax_macd.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5,prune='upper'))
            ax_macd.tick_params(axis='x',colors=spine_color)
            ax_macd.tick_params(axis='y',colors=spine_color, labelright=True)
            ax_macd.axes.yaxis.set_ticklabels([])
            ax_macd.set_xlim(datemin, datemax)
            ax_macd.xaxis.set_major_locator(mdates.MonthLocator())
            ax_macd.xaxis.set_major_formatter(mdates.DateFormatter('%B'))
            ax_macd.xaxis.set_minor_locator(mdates.WeekdayLocator(mdates.MONDAY))

            for label in ax_macd.xaxis.get_ticklabels():
                label.set_rotation(45)
            ax_macd.fill_between(date, self.df['MACD signal'], 0, alpha=0.5, facecolor=blue_color, edgecolor='k')

            '''
            ax_macd_der = ax_macd.twinx()
            ax_macd_der.plot(date, self.df['MACD_der'], color='k', linewidth=1, alpha=0.5)
            ax_macd_der.spines['bottom'].set_color(spine_color)
            ax_macd_der.spines['top'].set_color(spine_color)
            ax_macd_der.spines['left'].set_color(spine_color)
            ax_macd_der.spines['right'].set_color(spine_color)
            ax_macd_der.axes.yaxis.set_ticklabels([])
            #ax_macd.plot(date, self.df['MACD trigger'], color='k', linewidth=1)
            #ax_macd.fill_between(date, self.df['MACD signal'], 0, alpha=0.5, facecolor='g', edgecolor='k')
            ax_macd_der.set_xlim(datemin, datemax)
            '''

            # plot last week ---------------------------------------------------------------------------------------
            c_length = 7
            ax_lastweek = plt.subplot2grid((rowNum,colNum),(15,0),rowspan=4,colspan=2)
            plt.ylabel(str(c_length)+' day candlesticks',color=label_color)
            ax_lastweek.yaxis.label.set_color(spine_color)
            ax_lastweek.grid(True, color='k', alpha=0.5)
            ax_lastweek.spines['bottom'].set_color(spine_color)
            ax_lastweek.spines['top'].set_color(spine_color)
            ax_lastweek.spines['left'].set_color(spine_color)
            ax_lastweek.spines['right'].set_color(spine_color)
            ax_lastweek.tick_params(axis='y',colors=spine_color)
            ax_lastweek.tick_params(axis='x',colors=spine_color)
            ax_lastweek.xaxis.set_major_locator(mdates.DayLocator())
            ax_lastweek.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
            ax_lastweek.yaxis.set_major_locator(mticker.MaxNLocator(5, prune='both'))
            ax_lastweek.set_xlim(date.max() - c_length - 1, date.max() + 1)
            ax_main.xaxis.set_major_locator(mticker.MaxNLocator(prune='both'))

            # plot candlesticks
            candleAr = [[date[x],openp[x],closep[x],highp[x],lowp[x],volume[x]] for x in range(len(date)-c_length,len(date))]
            self.candlestick(ax_lastweek, candleAr[-c_length:], width=.5, colorup=good_color, colordown=bad_color)

            ax_lastweek.yaxis.tick_left()

            # points ---------------------------------------------------------------------------------------
            ax_description = plt.subplot2grid((rowNum,colNum),(15,2),rowspan=4,colspan=2)
            ax_description.grid(False)
            ax_description.get_xaxis().set_visible(False)
            ax_description.get_yaxis().set_visible(False)
            ax_description.spines['bottom'].set_color(spine_color)
            ax_description.spines['top'].set_color(spine_color)
            ax_description.spines['left'].set_color(spine_color)
            ax_description.spines['right'].set_color(spine_color)
            criteria_text = '\n'.join(['{}:'.format(x) for x in points])
            points_text = '\n'.join(['{}'.format(points[x]) for x in points])
            total_points = sum([points[x] for x in points])
            ax_description.text(0.03, 0.9, 'Total points: {}'.format(total_points), horizontalalignment='left', verticalalignment='top')
            ax_description.text(0.03, 0.7, criteria_text, horizontalalignment='left', verticalalignment='top')
            ax_description.text(0.25, 0.7, points_text, horizontalalignment='left', verticalalignment='top')


            # finished creating plot -----------------------------------------------------------------------

            signal_name = re.sub('[^0-9a-zA-Z]+', '-', signal_name)  # replace invalid filename chars

            if saveLocation == '':
                plt.show()
            else:
                pylab.savefig(saveLocation+signal_name + '.png', facecolor='w', edgecolor='w')
                if self.alt_file_path != None:
                    pylab.savefig(self.alt_file_path + signal_name + '.png', facecolor='w', edgecolor='w')
                plt.close()

        except BufferError:
        #except Exception as e:
            plt.close()
            print('failed to plot',signal_name,'because',e)

###########################################################################################################################################################
###      Graphing tools
###########################################################################################################################################################

    def normalize(self, signal):
        return [float(i)/sum(signal) for i in signal]

    def movingAverage(self, values,window):
        weights = np.repeat(1.0, window)/window
        return np.convolve(values, weights, 'valid')

    def expMovingAverage(self, values,window):
        weights = np.exp(np.linspace(-1.,0.,window))
        weights /= weights.sum()
        a = np.convolve(values,weights,mode='full')[:len(values)]
        a[:window] = a[window]
        return a

    def standard_deviation(self, date,tf,prices):
        sd = []
        sddate = []
        x = tf
        while x <= len(prices):
            a2c = prices[x-tf:x]
            standev = a2c.std()
            sd.append(standev)
            sddate.append(date[x])
            x+=1
        return sddate,sd

    def derivative(self, signal):
        return np.gradient(signal)

    def bbands(self, price, length=20, numsd=2):
        ave = price.rolling(window=length, center=False).mean()
        sd = price.rolling(window=length, center=False).std()
        upband = ave + (sd*numsd)
        dnband = ave - (sd*numsd)
        return np.round(ave,3), np.round(upband,3), np.round(dnband,3)

    def RSI(self, series, period = 14):
         delta = series.diff().dropna()
         u = delta * 0
         d = u.copy()
         u[delta > 0] = delta[delta > 0]
         d[delta < 0] = -delta[delta < 0]
         u[u.index[period-1]] = np.mean( u[:period] ) #first value is sum of avg gains
         u = u.drop(u.index[:(period-1)])
         d[d.index[period-1]] = np.mean( d[:period] ) #first value is sum of avg losses
         d = d.drop(d.index[:(period-1)])
         rs = u.ewm(ignore_na=False,min_periods=0,adjust=False,com=period-1).mean() / \
              d.ewm(ignore_na=False,min_periods=0,adjust=False,com=period-1).mean()
         return 100 - 100 / (1 + rs)

    def finalMinIndex(self, lowp):
        m1 = int(len(lowp)/2)
        for i in range(int(len(lowp)/2),int(3*len(lowp)/4)):
            if lowp[i] < lowp[m1]:
                m1 = i
        m2 = int(3*(len(lowp))/4)
        for i in range(int(3*len(lowp)/4),len(lowp)):
            if lowp[i] < lowp[m2]:
                m2 = i
        return m1, m2

    def finalMaxIndex(self, highp):
        m1 = int(len(highp)/2)
        for i in range(int(len(highp)/2),int(3*len(highp)/4)):
            if highp[i] > highp[m1]:
                m1 = i
        m2 = int(3*(len(highp))/4)
        for i in range(int(3*len(highp)/4),len(highp)):
            if highp[i] > highp[m2]:
                m2 = i
        return m1, m2

    def rangeLimit(self, v,l,h):
        if v < l:
            v = l
        if v > h:
            v = h
        return v

    def average(self, l):
        return sum(l)/len(l)

    def increasingness(self, signal):
        shortTerm = signal[-1] - self.average(signal[-3:])
        longTerm = self.average(signal[-3:]) - self.average(signal[-10:-3])
        return self.average([shortTerm, longTerm])

    def candlestick(self, ax, quotes, width=0.4, colorup='k', colordown='r',
                 alpha=1.0, ochl=True):
        OFFSET = width / 2.0
        lines = []
        patches = []
        for q in quotes:
            if ochl:
                t, open, close, high, low = q[:5]
            else:
                t, open, high, low, close = q[:5]

            if close >= open:
                color = colorup
                lower = open
                height = close - open
            else:
                color = colordown
                lower = close
                height = open - close

            vline = Line2D(
                xdata=(t, t), ydata=(low, high),
                color=color,
                linewidth=0.7,
                antialiased=True,
            )

            rect = Rectangle(
                xy=(t - OFFSET, lower),
                width=width,
                height=height,
                facecolor=color,
                edgecolor=color,
            )
            rect.set_alpha(alpha)

            lines.append(vline)
            patches.append(rect)
            ax.add_line(vline)
            ax.add_patch(rect)
        ax.autoscale_view()
        ax.yaxis.tick_right()

        return lines, patches


###########################################################################################################################################################
###      Email
###########################################################################################################################################################


    def send_email(self, directory, title, mailing_list):

        with open(self.par_path + '/auth/takaomattpython.txt') as f:
        	password = f.read()

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login('takaomattpython@gmail.com', password)

        msg = MIMEMultipart()
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = title+': '+str(formatdate(localtime=True))

        fList = []
        for file in os.listdir(directory):
            fList.append(directory + file)

        for f in fList:
            with open(f, "rb") as fil:
                part = MIMEApplication(
                    fil.read(),
                    Name=basename(f)
                )
                part['Content-Disposition'] = 'attachment; filename="%s"' % basename(f)
                msg.attach(part)

        print('Emails away!')

        for i in mailing_list:
            server.sendmail('takaomattpython@gmail.com', i, msg.as_string())
        server.quit()

# for debugging
'''
stock = 'CMI'
C = CapitVita()
#C.graph_data(stock)
C.find_stocks()
'''
