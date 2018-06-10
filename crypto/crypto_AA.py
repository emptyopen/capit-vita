###
# Takeezi
###

from capit_vita_crypto import CapitVitaCrypto
import cProfile
import pstats
import os

home_path = '/Users/takaomatt/Documents/python-projects/capit-vita-v2/'  ## <---------------- change me
home_path = 'C:/Users/wc803e/Documents/python/scripts/self/'
home_path = 'C:/Users/Takkeezi/Documents/python/capit-vita-2/'

mailing_list = ['takaomatt@gmail.com']  ## <---------------- change me
mailing_list = []  # when debugging

def my_function():
    C = CapitVitaCrypto(home_path = home_path, num_coins = 30,
        mailing_list = mailing_list, debug = False)
    #C.find_coins(graph = True)
    #C.buy_altcoin('ZEC')
    C.my_coin_price_change()

    C.total_available_USD(False)



'''
cProfile.run('my_function()', 'stats.txt')
p = pstats.Stats('stats.txt')
os.remove('stats.txt')
p.sort_stats('cumulative').print_stats(10)
'''

my_function()










##
