from capit_vita import CapitVita
import cProfile
import pstats
import os

mailing_list = ['takaomatt@gmail.com']
#mailing_list = []

def my_function():
    C = CapitVita(num_stocks = 30, mailing_list = mailing_list, debug = False)
    C.find_stocks(graph = True)

'''
cProfile.run('my_function()', 'stats.txt')
p = pstats.Stats('stats.txt')
#p.strip_dirs().sort_stats(-1).print_stats()
p.sort_stats('cumulative').print_stats(10)
'''

my_function()
