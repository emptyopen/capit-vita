###
# Takeezi
###

import os
import re
import glob
import time
import datetime
import urllib2
import json
from operator import itemgetter
import pandas as pd

from capit_vita_plot import CapitVita
from bittrex import Bittrex
from emails_away import send_email

# capit-vita for cryptocurrency

# To-do
'''
Clean everything up hellaaaa

Confirm commission is just 0.35%

Have a list at all times of coins to buy (update file with a 'find_coins', but remove any coins that I already own to avoid duplications)
If a coin goes +/- 10%, sell that coin and buy the next coin on the list (pop the coin from file)

Update wanted_coins every 8 hours?
Check on coin stats every 1 hour?
'''

with open(os.pardir + '/auth/bittrex.txt') as f:
	bittrex_key_secret = f.read().split('\n')
key = bittrex_key_secret[0]
secret = bittrex_key_secret[1]

class CapitVitaCrypto(CapitVita):

    def __init__(self, home_path = '', num_coins = 25, mailing_list = [], debug = False):

        self.num_coins = num_coins
        self.mailing_list = mailing_list
        self.coin_list = []
        self.df = []
        self.debug = debug
        self.home_path = home_path
        self.file_path = home_path + 'crypto-data/'
        self.volume_sum = []

        # bittrex
        self.B = Bittrex(key, secret)
        self.b_currencies = [x['Currency'] for x in self.B.get_currencies()['result']]  # currencies available to trade in bittrex
        self.market_summaries = self.B.get_market_summaries()['result']
        self.markets = [x['MarketName'] for x in self.market_summaries]  # market names
        self.BTC_markets = [x for x in self.markets if 'BTC' in x and 'USDT' not in x]
        self.ETH_markets = [x for x in self.markets if 'ETH' in x and 'USDT' not in x]
        self.USDT_markets = [x for x in self.markets if 'USDT' in x]
        self.USDT_BTC = [x for x in self.market_summaries if x['MarketName'] == 'USDT-BTC'][-1]['Last']
        self.USDT_ETH = [x for x in self.market_summaries if x['MarketName'] == 'USDT-ETH'][-1]['Last']

    def get_coin_list(self):
        # get coin list (all coins, some are not tradeable on bittrex)

        url = 'https://www.cryptocompare.com/api/data/coinlist/'
        response = urllib2.urlopen(url)
        data = json.loads(response.read())
        self.coin_list = [x.encode('ascii', 'ignore') for x in data['Data'].keys()]
        #print(len(self.coin_list))   # 1507 as of 2017-09-14


    def grab_data(self, coin):
        # get historical OHLC for one cryptocurrency

        url = 'https://min-api.cryptocompare.com/data/histoday?fsym={}&tsym=USD&limit={}&aggregate=1&e=CCCAGG'.format(coin, 80)
        response = urllib2.urlopen(url)
        data = json.loads(response.read())

        try:
            self.df = pd.DataFrame(data['Data'])
            self.df['date'] = self.df['time'].apply(lambda x: datetime.datetime.fromtimestamp(x))
            #self.df.drop(['time', 'volumefrom'], axis = 1)
            #self.df.columns = ['Adj. Close', 'Adj. High', 'Adj. Low', 'Adj. Open', 'time', 'volumefrom', 'volumeto', 'date']
        except KeyError:
            return False

        self.volume_sum.append(self.df['volumeto'].iloc[-20:].median())

        # generate signals
        self.df['rsi'] = self.RSI(self.df['close'], 14)
        self.df['26 ema'] = self.df['close'].ewm(ignore_na=False,min_periods=0,adjust=True,com=26).mean()
        self.df['12 ema'] = self.df['close'].ewm(ignore_na=False,min_periods=0,adjust=True,com=12).mean()
        self.df['MACD'] = self.df['12 ema'] - self.df['26 ema']
        self.df['MACD signal'] = self.df['MACD'] - self.df['MACD'].ewm(ignore_na=False,min_periods=0,adjust=True,com=9).mean()
        self.df['MACD_norm'] = self.normalize(self.df['MACD signal'])
        self.df['MACD_der'] = self.derivative(self.df['MACD_norm'])


    def get_points(self, coin):

        try:

            self.grab_data(coin)  ## get the data and store it in self.df

            if len(self.df) < 20 or self.df['volumeto'].iloc[-20:].median() < 850000 * 0.8:  # if grab is unsuccessful or below average volume * 0.7, end
                points = {'admin':-500}

            else:
                points = {}

                mb, tb, bb, = self.bbands(self.df['close'])
                if self.df['close'].iloc[-1] < (mb.iloc[-1] + bb.iloc[-1]) / 2:
                    points['admin'] = -500

                # RSI points (max 50)
                points['rsi'] = 50 - round(1.2 * abs(30-self.df['rsi'].iloc[-1]))

                # MACD points (max 50)
                points['macd1'] = round(25 * self.df['MACD_norm'].iloc[-1] / max([abs(x) for x in self.df['MACD_norm']]))
                points['macd2'] = round(25 * self.df['MACD_der'].iloc[-1] / max([abs(x) for x in self.df['MACD_der']]))

                # candlestick points (max 10)
                candlestickFactor = 1

                patterns = self.detectCandlestickPatterns(self.df['open'][-7:],
                                    self.df['close'][-7:], self.df['low'][-7:],
                                    self.df['high'][-7:], candlestickFactor)
                points['candlesticks'] = self.rangeLimit(round(sum([x[2] for x in patterns])), -20, 20)

        except BufferError as e:
        #except Exception as e:
            print('problem: {}'.format(e))

        return points


    def find_coins(self, graph = False, bittrex_currencies_only = True):
        # start counting duration of script
        start_time = time.time()

        print('Initiating log...')
        # create log
        ff = open(self.file_path+'readme.txt','w')
        ff.write(str(datetime.datetime.now()))
        ff.write('\n')

        print('Deleting old plots...')
        # delete old files
        os.chdir(self.file_path)
        filelist = glob.glob('*.png')
        for f in filelist:
            os.remove(f)
        os.chdir(self.home_path)

        print('Fetching coin list...')
        if bittrex_currencies_only:
            self.update_B()
            self.coin_list = self.b_currencies
        else:
            self.get_coin_list()
            if self.debug:
                self.coin_list = self.coin_list[:30]

        len_coin_list = len(self.coin_list)
        print('  {} coins.'.format(len_coin_list))
        #print('  Expect script to take approximately {} minutes'.format(round(len_coin_list*1.0613 - 14)/60, 2))

        # grab data in batches
        print('Getting points for {} coins...'.format(len_coin_list))
        coin_points = {}
        for i, coin in enumerate(self.coin_list):
            if i % (len(self.coin_list) / 25) == 0:
                print('{}% done'.format(round(100 * float(i) / len(self.coin_list), 1)))
            try:
                points = self.get_points(coin)
                coin_points[coin] = [sum([points[x] for x in points]), points]
            #except BufferError:
            except Exception as e:
                print('failed {} because {}'.format(coin, e))
        original_len_coin_list = len(coin_points)

        print('Sorting coins...')
        # sort stocks by point system
        sorted_coins = sorted(coin_points.items(), key=itemgetter(1), reverse = True)[:self.num_coins]

        print(sorted_coins)

        if graph:
            print('Graphing coins...')
            for coin in [x[0] for x in sorted_coins]:
                try:
                    self.graph_data(coin, saveLocation = self.file_path)
                except BufferError:
                #except Exception as e:
                    print('failed {} because {}'.format(coin, e))

        # write into log
        ff.write('Cheap coins to invest in for 2 days ~ 1 week: \n\n')

        ff.write('#\n')
        for i in sorted_coins:
            ff.write(i[0]+': '+str(round(i[1][0],1))+'  '+str(i[1][1])+'\n')
        ff.write('#\n')

        ff.write('\n\n  '+str(original_len_coin_list)+' stocks shortened by point system to '+str(len(sorted_coins))+' stocks')

        ff.write("\n\n--- %s seconds ---" % (round(time.time() - start_time, 2)))

        ff.write('\n\n\n  Capit-Vita Crypto Version 1.1  (2017-09-22)\n\n')
        ff.write('  - Buying is confirmed to work\n')
        ff.close()

        #print(self.volume_sum[-20:])
        #print('average volume', sum(self.volume_sum)/len(self.volume_sum))
        # median volumeto: 850k

        # send email
        if len(self.mailing_list) > 0:
            send_email(self.file_path, 'Top '+str(self.num_coins)+' Coin Prospects', self.mailing_list)

        ###### remove coin types I currently own
        my_coins = [x['Currency'] for x in self.B.get_balances()['result']]
        print('my coins: {}'.format(my_coins))
        print('before: {}'.format([x[0] for x in sorted_coins]))
        sorted_coins = [x for x in sorted_coins if x[0] not in my_coins]
        print('after: {}'.format([x[0] for x in sorted_coins]))

        # save wanted coins
        with open(self.file_path+'wanted_coins.txt', 'w') as f:
            f.write('{}, '.format([str(x[0]) for x in sorted_coins]))

        return sorted_coins

    def buy_next_coin(self):

        # save wanted_coins
        if os.path.isfile(self.file_path+'wanted_coins.txt'):
            with open(self.file_path+'wanted_coins.txt', 'r') as f:
                data = eval(f.readlines()[0][:-2])
        else:
            return False

        print(data)



    def update_B(self):

        self.b_currencies = [x['Currency'] for x in self.B.get_currencies()['result']]  # currencies available to trade in bittrex
        self.market_summaries = self.B.get_market_summaries()['result']
        self.markets = [x['MarketName'] for x in self.market_summaries]  # market names
        self.BTC_markets = [x for x in self.markets if 'BTC' in x and 'USDT' not in x]
        self.ETH_markets = [x for x in self.markets if 'ETH' in x and 'USDT' not in x]
        self.USDT_markets = [x for x in self.markets if 'USDT' in x]
        self.USDT_BTC = [x for x in self.market_summaries if x['MarketName'] == 'USDT-BTC'][-1]['Last']
        self.USDT_ETH = [x for x in self.market_summaries if x['MarketName'] == 'USDT-ETH'][-1]['Last']
        #print len(self.b_currencies) # 277 as of 2017-09-21

    def thing(self):


        BTC_market_prices = []
        ETH_market_prices = []
        ### create value exchange rate
        for currency in self.b_currencies:
            if any(currency in x for x in BTC_markets):
                last_price = [x['Last'] for x in self.market_summaries if x['MarketName'] == 'BTC-{}'.format(currency)]
                if len(last_price) > 0:
                    BTC_market_prices.append('Last price for {} is ${}'.format(currency, round(last_price[0] * USDT_BTC, 2)))
            elif any(currency in x for x in ETH_markets):
                last_price = [x['Last'] for x in self.market_summaries if x['MarketName'] == 'ETH-{}'.format(currency)]
                if len(last_price) > 0:
                    ETH_market_prices.append('Last price for {} is ${}'.format(currency, round(last_price[0] * USDT_ETH, 2)))

        cnt_in = 0
        cnt_not_in = 0
        for currency in self.b_currencies:
            if all(currency not in x for x in self.BTC_markets + self.ETH_markets):
                cnt_not_in += 1
                #print('{} not in any market'.format(currency))
            else:
                cnt_in += 1

        #print(cnt_in, cnt_not_in) #203 in market, 74 out of market as of 2017-09-21

        ### can only buy and sell on existing markets


    def my_coins(self):

        my_coins = [x for x in self.B.get_balances()['result']]
        print(my_coins)
        total = 0
        print('\n\n-----------  My Wallet -----------\n')
        for coin in my_coins:
            if coin['Currency'] == 'BTC':
                print('{} available for {} (${})'.format(coin['Available'], coin['Currency'], round(coin['Available'] * self.USDT_BTC, 2)))
                total += coin['Available'] * self.USDT_BTC
            elif any(coin['Currency'] in x for x in self.BTC_markets):
                BTC_coin_rate = [x['Last'] for x in self.market_summaries if x['MarketName'] == 'BTC-{}'.format(coin['Currency'])][0]
                print('{} available for {} (${})'.format(coin['Available'], coin['Currency'], round(coin['Available'] * self.USDT_BTC * BTC_coin_rate, 2)))
                total += coin['Available'] * self.USDT_BTC * BTC_coin_rate
            else:
                print('{} available for {} (${})'.format(coin['Available'], coin['Currency'], 'hold')) ## add ethereum
        #return summary
        return my_coins


    def total_available_USD(self, BTC_ETH_only = True):

        balances = self.B.get_balances()['result']
        total_USD = 0

        for balance in balances:
            if balance['Balance'] > 0:
                if balance['Currency'] == 'BTC':
                    total_USD += balance['Balance'] * self.USDT_BTC
                    print('BTC: {}'.format(balance['Balance'] * self.USDT_BTC))
                elif balance['Currency'] == 'ETH':
                    total_USD += balance['Balance'] * self.USDT_ETH
                    print('ETH: {}'.format(balance['Balance'] * self.USDT_ETH))
                elif not BTC_ETH_only:
                    if any(balance['Currency'] in x for x in self.BTC_markets):
                        to_add = balance['Balance'] * [x['Last'] for x in self.market_summaries if x['MarketName'] == 'BTC-{}'.format(balance['Currency'])][0] * self.USDT_BTC
                        total_USD += to_add
                        print('{}: {}'.format(balance['Currency'], to_add))
                    elif any(balance['Currency'] in x for x in self.ETH_markets):
                        to_add = balance['Balance'] * [x['Last'] for x in self.market_summaries if x['MarketName'] == 'ETH-{}'.format(balance['Currency'])][0] * self.USDT_ETH
                        total_USD += to_add
                        print('{}: {}'.format(balance['Currency'], to_add))
                # consider only BTC and ETH liquid?

        print('Total available: {}'.format(total_USD))

        return total_USD


    def buy_altcoin(self, coin):

        if any(coin in x['Currency'] for x in self.B.get_balances()['result']):
            print('not buying, already have')
            return False

        if any(coin in x for x in self.BTC_markets):

            market = [x for x in self.BTC_markets if coin in x][0]
            print(market)

            available_USD = self.total_available_USD()
            print('available USD', available_USD)

            increment_USD = available_USD / 20
            print('5% available USD: {}'.format(increment_USD))

            BTC_coin_rate = self.B.get_marketsummary(market)['result'][0]['Last']
            print('BTC - {} conversion: {}'.format(coin, BTC_coin_rate))

            print('BTC - USD conversion: {}'.format(self.USDT_BTC))

            print('want to buy {} {} coins'.format(increment_USD / self.USDT_BTC / BTC_coin_rate, coin))

            print('buying {}: {}'.format(coin, self.B.buy_limit(market, increment_USD / self.USDT_BTC / BTC_coin_rate, BTC_coin_rate)))    # market, quantity, rate

    def sell_altcoin(self, order):
        # takes a buy order and reverses it (sell)

        coin = order['Exchange'][4:]
        if any(coin in x for x in self.BTC_markets):
            market = [x for x in self.BTC_markets if coin in x][0]
        elif any(coin in x for x in self.ETH_markets):
            market = [x for x in self.ETH_markets if coin in x][0]
        coin_rate = self.B.get_marketsummary(market)['result'][0]['Last']
        quantity = order['Quantity']

        if all(coin not in x['Currency'] for x in self.B.get_balances()['result']):
            print('cannot sell, do not have')
            return False

        #print('selling {}: {}'.format(market, self.B.sell_limit(market, quantity, coin_rate)))    # market, quantity, rate


    def coin_to_USD(self, order):

        coin = order['Exchange'][4:]

        market = [x for x in self.BTC_markets if coin in x][0]
        BTC_coin_rate = self.B.get_marketsummary(market)['result'][0]['Last']

        if coin == 'BTC':
            return order['Quantity'] * self.USDT_BTC
        elif coin == 'ETH':
            pass
        elif any([coin in x for x in self.BTC_markets]):
            last_price = [x['Last'] for x in self.market_summaries if coin in x['MarketName']]
            return order['Quantity'] * self.USDT_BTC * BTC_coin_rate
        elif any(coin in x for x in self.ETH_markets):
            pass
        else:
            pass


    def my_coin_price_change(self):

        orders = self.B.get_order_history()['result']

        ## remove orders that I don't own
        orders = [x for x in orders]

        print(orders)

        self.update_B()

        for order in orders:
            bought_at = round(order['Quantity'] * order['PricePerUnit'] * self.USDT_BTC, 2)
            currently = round(self.coin_to_USD(order), 2)
            perc_change = round((currently / bought_at - 1) * 100, 1)
            timestamp = datetime.datetime.now() - datetime.datetime.strptime(order['TimeStamp'], '%Y-%m-%dT%H:%M:%S.%f')
            print('   bought {} ({} ago) for relative BTC value of ${}, currently ${}: {}% change'.format(order['Exchange'][4:], timestamp, bought_at, currently, perc_change))

            ### formula for selling:
                # cost of trade = 0.35% x 2 = 0.7%
                # have an open sell order at 10% -> 9.3% up
                # if simulataneous orders are possible, have an open sell order at -10% -> 10.7% down
                # if the coin is older than 5 days, lower the upper sell limit by 2% to 8% -> 7.3% up
                # every 3 days after that lower by 2% until @ 2%

            lower_limit = -10
            if timestamp < datetime.timedelta(days = 5):
                upper_limit = 10
            elif timestamp < datetime.timedelta(days = 8): # approx one week
                upper_limit = 8
            elif timestamp < datetime.timedelta(days = 11):
                upper_limit = 6
            elif timestamp < datetime.timedelta(days = 14): # two weeks
                upper_limit = 4
            elif timestamp < datetime.timedelta(days = 17):
                upper_limit = 2
            elif timestamp > datetime.timedelta(days = 21): # sell no matter what after 3 weeks
                upper_limit = -10

            if perc_change < lower_limit or perc_change > upper_limit:
                self.sell_altcoin(order)

















#
