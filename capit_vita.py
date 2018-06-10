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
email alphavantage key
auto sell architecture
filter out already bought options
show 3 months empty ahead of time
show points in plot
improve MACD plot? revamp point system and technical indicators
https://www.investopedia.com/articles/active-trading/011815/top-technical-indicators-rookie-traders.asp
'''


class CapitVita(object):

    def __init__(self, title = '', num_stocks = 15, mailing_list = [], debug = False):

        self.title = title
        self.num_stocks = num_stocks
        self.home_path = os.path.abspath(os.getcwd())
        print(self.home_path, '/home/ec2-user', self.home_path == '/home/ec2-user')
        if 'ec2-user' in self.home_path:
            self.home_path = '/home/ec2-user/capit-vita'
        self.file_path = self.home_path+'/data/'
        self.par_path = os.path.dirname(self.home_path) + '/'
        self.home_path = self.home_path + '/'
        if os.path.exists(self.par_path + '/takaomattcom/static/img/stocks/'):
            print('path exists')
            self.alt_file_path = self.par_path + '/takaomattcom/static/img/stocks/'
        else:
            print('path does not exist')
            self.alt_file_path = None
        print('capit', self.home_path, self.file_path, self.par_path, self.alt_file_path)
        self.mailing_list = mailing_list
        self.debug = debug
        self.batchSize = 50

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
        os.chdir(self.home_path+'temp/')
        filelist = glob.glob("*.csv")
        for f in filelist:
            os.remove(f)
        if self.alt_file_path != None:
            os.chdir(self.alt_file_path)
            filelist = glob.glob('*.png')
            for f in filelist:
                os.remove(f)
        os.chdir(self.home_path)

        print('Fetching stock list...')
        if os.path.isfile(self.home_path + '20170718-options.txt'):
            print('  Using weekly :)')
            with open(self.home_path+'20170718-options.txt', 'r') as f:
                stockset = list(f.read().split(','))[:-2]
        else:
            print('  Using all :(')
            with open(self.home_path+'stockListAll.txt', 'r') as f:
                stockset = list(f.read().split(','))
        if self.debug:
            stockset = stockset[:10]
        lenStockset = len(stockset)

        print('Grabbing data for {} stocks...'.format(lenStockset))
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


    def grab_data(self, signal_name):

        try:

            with open(self.par_path + '/auth/alphavantage.txt') as f:
            	myAPI = f.read().split('\n')[0]
            tries = 0
            while True:
                url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={}&outputsize=full&apikey={}'.format(signal_name, myAPI)
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
            self.df = self.df.iloc[-100:]
            self.df.columns = ['open', 'high', 'low', 'close', 'adjusted close', 'volume', 'dividend amount', 'split coefficient']
            self.df[['open','high','low','close','volume']] = self.df[['open','high','low','close','volume']].apply(pd.to_numeric)
            self.df['rsi'] = self.RSI(self.df['close'], 14)
            self.df['26 ema'] = self.df['close'].ewm(ignore_na=False,min_periods=0,adjust=True,com=26).mean()
            self.df['12 ema'] = self.df['close'].ewm(ignore_na=False,min_periods=0,adjust=True,com=12).mean()
            self.df['MACD'] = self.df['12 ema'] - self.df['26 ema']
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

    def get_points(self, signal_name, criteria = {}, rng = '1y'):

        try:

            points = {}

            self.grab_data(signal_name)

            mb, tb, bb, = self.bbands(self.df['close'])
            if self.df['close'].iloc[-1] < (mb.iloc[-1] + bb.iloc[-1]) / 2:
                points['admin'] = -500

            if len(self.df['close']) < 100:
                points['admin'] = -500

            # RSI points (max 50)
            points['rsi'] = 50 - round(1.2 * abs(30-self.df['rsi'].iloc[-1]))

            # MACD points (max 50)
            points['macd1'] = round(15 * self.df['MACD_norm'].iloc[-1] / max([abs(x) for x in self.df['MACD_norm']]))
            points['macd2'] = round(15 * self.df['MACD_der'].iloc[-1] / max([abs(x) for x in self.df['MACD_der']]))

            # candlestick points (max 10)
            #if style == 'option':
            candlestickFactor = 0

            patterns = self.detectCandlestickPatterns(self.df['open'][-7:],
                                self.df['close'][-7:], self.df['low'][-7:],
                                self.df['high'][-7:], candlestickFactor)
            points['candlesticks'] = self.rangeLimit(round(sum([x[2] for x in patterns])), -20, 20)

            # guru points (max 80)
            try:
                guru = self.get_guru(signal_name)
                points['guru_financial'] = 3.5*int(guru[0])
                points['guru_growth'] = 3.5*int(guru[1])
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

    def graph_data(self, signal_name, rng = 150, saveLocation = ''):
                            # sdq = side, date, quantity
        try:

            # create signals
            self.grab_data(signal_name)

            # grab data
            #self.df = self.df.iloc[-rng:]
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

            #ns = 1e-9
            #date = [dt.datetime.utcfromtimestamp(x.astype(int)*ns) for x in date]
            #date = mdates.date2num(date)

            # make colors
            goodColor = '#53C156'
            badColor = '#ff1717'
            spineColor = '#5998ff'

            rowNum = 10
            colNum = 4

            # identify fig
            #fig = plt.figure(facecolor='w',figsize=(18.,11.))
            plt.figure(facecolor='w',figsize=(18.,11.))
            plt.suptitle(signal_name,color=spineColor, size='xx-large')
            plt.subplots_adjust(left=.09,bottom=.04,right=.94,top=.95,wspace=.2,hspace=0)

            # initialize params
            bbtf = 20

            # plot 0 ---------------------------------------------------------------------------------------
            ax0 = plt.subplot2grid((rowNum,colNum),(0,0),rowspan=1,colspan=4,facecolor='w')
            plt.ylabel('RSI',color='k')
            ax0.yaxis.label.set_color(spineColor)
            ax0.spines['bottom'].set_color(spineColor)
            ax0.spines['top'].set_color(spineColor)
            ax0.spines['left'].set_color(spineColor)
            ax0.spines['right'].set_color(spineColor)
            ax0.tick_params(axis='y',colors=spineColor)
            ax0.set_yticks([30,70])
            ax0.axhline(70,color = badColor)
            ax0.axhline(30,color = goodColor)
            plt.setp(ax0.get_xticklabels(),visible=False)

            # plot RSI
            ax0.plot(date, self.df['rsi'], color='k')
            pylab.ylim([0,100])

            # plot 0v ---------------------------------------------------------------------------------------
            ax0v = ax0.twinx()
            ax0v.grid(False)
            ax0v.axes.yaxis.set_ticklabels([])
            ax0v.yaxis.label.set_color(spineColor)
            ax0v.spines['bottom'].set_color(spineColor)
            ax0v.spines['top'].set_color(spineColor)
            ax0v.spines['left'].set_color(spineColor)
            ax0v.spines['right'].set_color(spineColor)
            ax0v.tick_params(axis='y',colors=spineColor)
            #plt.setp(ax0v.get_xticklabels(),visible=False)

            # plot 1 ---------------------------------------------------------------------------------------
            ax1 = plt.subplot2grid((rowNum,colNum),(1,0),rowspan=5,colspan=4,facecolor='w',sharex=ax0)

            plt.ylabel('Price and Volume',color=spineColor)
            ax1.grid(True,color=spineColor)
            #ax1.xaxis.set_major_locator(mticker.MaxNLocator(10))
            #ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax1.yaxis.label.set_color(spineColor)
            ax1.spines['bottom'].set_color(spineColor)
            ax1.spines['top'].set_color(spineColor)
            ax1.spines['left'].set_color(spineColor)
            ax1.spines['right'].set_color(spineColor)
            ax1.tick_params(axis='y',colors=spineColor)
            plt.setp(ax1.get_xticklabels(),visible=False)
            plt.gca().yaxis.set_major_locator(mticker.MaxNLocator(prune='upper')) #prune
            ax1.xaxis.set_major_locator(mticker.MaxNLocator(nbins=20))


            # plot Bollinger bands
            mb, tb, bb, = self.bbands(closep)
            ax1.plot(date,tb,'#adbdd6',alpha=0.7,label='TB')
            ax1.plot(date,bb,'#adbdd6',alpha=0.7,label='BB')
            ax1.plot(date,mb,'#ba970d',alpha=0.7,label='MA'+str(bbtf))


            # min max stuff
            min1, min2 = self.finalMinIndex(lowp)
            max1, max2 = self.finalMaxIndex(highp)
            d1 = int((min1+max1)/2)
            d2 = int((min2+max2)/2)
            ax1.plot([date[d1],date[d2]],[closep[d1],closep[d2]],linewidth=7,color='#4ee6fd',alpha=0.8,linestyle=':')


            # plot candlestick
            candleAr = [[date[x],openp[x],closep[x],highp[x],lowp[x]] for x in range(len(date))]
            self.candlestick(ax1, candleAr, width = 0.5, colorup = goodColor, colordown = badColor)


            # plot 1v ---------------------------------------------------------------------------------------
            ax1v = ax1.twinx()
            ax1v.grid(False)
            ax1v.axes.yaxis.set_ticklabels([])
            ax1v.spines['bottom'].set_color(spineColor)
            ax1v.spines['top'].set_color(spineColor)
            ax1v.spines['left'].set_color(spineColor)
            ax1v.spines['right'].set_color(spineColor)
            ax1v.yaxis.label.set_color(spineColor)
            ax1v.xaxis.label.set_color(spineColor)
            ax1v.set_ylim(0,2*volume.max())
            ax1v.tick_params(axis='x',colors='w')
            ax1v.tick_params(axis='y',colors='w')

            # plot volume
            ax1v.fill_between(date,0,volume,facecolor='#8e8e87',alpha=.1)

            # plot 2 ---------------------------------------------------------------------------------------
            ax2 = plt.subplot2grid((rowNum,colNum),(6,0),rowspan=1,colspan=4,facecolor='w',sharex=ax0)
            plt.ylabel('MACD',color=spineColor)
            ax2.grid(True,color=spineColor)
            ax2.yaxis.label.set_color(spineColor)
            ax2.spines['bottom'].set_color(spineColor)
            ax2.spines['top'].set_color(spineColor)
            ax2.spines['left'].set_color(spineColor)
            ax2.spines['right'].set_color(spineColor)
            ax2.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5,prune='upper'))
            ax2.tick_params(axis='x',colors=spineColor)
            ax2.tick_params(axis='y',colors=spineColor)
            ax2.xaxis.label.set_color(spineColor)
            xfmt = mdates.DateFormatter('%Y-%m-%d')
            ax2.xaxis.set_major_formatter(xfmt)
            for label in ax2.xaxis.get_ticklabels():
                label.set_rotation(45)

            ax2.fill_between(date, self.df['MACD_norm'], 0, alpha=0.5, facecolor='#4ee6fd', edgecolor='k')


            MACD_min = abs(round(min(self.df['MACD_norm']), 2))
            MACD_max = abs(round(max(self.df['MACD_norm']), 2))
            if MACD_min > MACD_max:
                lim = MACD_min
            else:
                lim = MACD_max
            ax2.set_ylim(-lim*1.1, lim*1.1)

            # plot 2v ---------------------------------------------------------------------------------------

            ax2v = ax2.twinx()
            ax2v.axes.yaxis.set_ticklabels([])
            ax2v.spines['bottom'].set_color(spineColor)
            ax2v.spines['top'].set_color(spineColor)
            ax2v.spines['left'].set_color(spineColor)
            ax2v.spines['right'].set_color(spineColor)

            ax2v.fill_between(date, self.df['MACD_der'], 0, alpha=0.5, facecolor='#eaed4d', edgecolor='k')

            MACD_der_min = abs(round(min(self.df['MACD_der']), 2))
            MACD_der_max = abs(round(max(self.df['MACD_der']), 2))
            if MACD_der_min > MACD_der_max:
                lim = MACD_der_min
            else:
                lim = MACD_der_max
            ax2v.set_ylim(-lim*1.1, lim*1.1)


            # plot 5 ---------------------------------------------------------------------------------------
            cLength = 7
            ax5 = plt.subplot2grid((rowNum,colNum),(8,0),rowspan=2,colspan=2,facecolor='w')
            plt.ylabel(str(cLength)+' day candlesticks',color=spineColor)
            ax5.yaxis.label.set_color(spineColor)
            ax5.grid(True, color='k', alpha=0.5)
            ax5.spines['bottom'].set_color(spineColor)
            ax5.spines['top'].set_color(spineColor)
            ax5.spines['left'].set_color(spineColor)
            ax5.spines['right'].set_color(spineColor)
            ax5.tick_params(axis='y',colors=spineColor)

            # plot candlestick
            candleAr = [[date[x],openp[x],closep[x],highp[x],lowp[x],volume[x]] for x in range(len(date)-cLength,len(date))]
            self.candlestick(ax5, candleAr[-cLength:], width=.5, colorup=goodColor, colordown=badColor)

            xfmt = mdates.DateFormatter('%a')
            ax5.xaxis.set_major_formatter(xfmt)

            # plot 6 ---------------------------------------------------------------------------------------
            ax6 = plt.subplot2grid((rowNum,colNum),(8,2),rowspan=2,colspan=1,facecolor='w')
            ax6.grid(False)
            ax6.spines['bottom'].set_color(spineColor)
            ax6.spines['top'].set_color(spineColor)
            ax6.spines['left'].set_color(spineColor)
            ax6.spines['right'].set_color(spineColor)

            # plot 7 ---------------------------------------------------------------------------------------
            ax7 = plt.subplot2grid((rowNum,colNum),(8,3),rowspan=2,colspan=1,facecolor='w')
            ax7.grid(False)
            ax7.spines['bottom'].set_color(spineColor)
            ax7.spines['top'].set_color(spineColor)
            ax7.spines['left'].set_color(spineColor)
            ax7.spines['right'].set_color(spineColor)

                # nothing here currently


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

    def bbands(self, price, length=30, numsd=2):
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



stock = 'cgnx'
C = CapitVita()
C.graph_data(stock)
