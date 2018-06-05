from Robinhood import Robinhood
from tabulate import tabulate
from datetime import datetime, timedelta
from find_good_stocks import FGS
from emails_away import sendEmail
import sqlite3, os, glob, time

# robinhood analysis and action

# login
# sell any stocks greater than 5% or less than -5%
# sell any stocks greater than 0% and if more than 5 days have elapsed
# sell any stocks if more than 10 days have elapsed
# if money is available, buy ranked #1 stock
# email updates

# robinhood.securities_owned returns:
#      [ stock_name, quantity, date_bought, average_buy_price, current_price ]

home_path = os.path.abspath(os.getcwd())
print(home_path, '/home/ec2-user', home_path == '/home/ec2-user')
if 'ec2-user' in home_path:
    home_path = '/home/ec2-user/capit-vita'
file_path = self.home_path+'/data/'
par_path = os.path.dirname(self.home_path) + '/'
home_path = self.home_path + '/'

with open(os.pardir + '/auth/takaomattpython.txt') as f:
	password = f.read()

with open(os.pardir + '/auth/takaomattpython.txt') as f:
	data = f.read().split('\n')
    usrnm = data[0]
    psswrd = data[1]

class Robinhood_AA (object):

    def __init__(self):
        self.start_time = datetime.now()
        self.my_trader = Robinhood()
        self.my_trader.login(username=usrnm, password=pssw)
        self.equity = self.my_trader.equity()
        self.owned_securities = self.my_trader.securities_owned()
        self.available_funds = self.my_trader.equity() - sum([x[1]*x[4] for x in self.my_trader.securities_owned()])
        self.buy_limit = 120
        self.stocks = []
        self.ld = 10  ## sell no matter what
        self.sd = 5  ## sell if positive
        self.file_path = home_path
        self.conn = sqlite3.connect(self.file_path+'log.db')
        self.conn.execute('drop table if exists history')
        self.conn.execute('''create table history
                (id int primary key     not null,
                date            text    not null,
                activity        text    not null,
                stock           text    not null,
                gain            text    not null);''')
        self.idCount = 1
        print('Deleting old files...')
        # delete old files
        os.chdir(self.file_path)
        for f in glob.glob("*.png"):
            os.remove(f)

    def today_stocks_to_buy(self):
        F = FGS('Low Cost', 100, {'minPrice':7,'maxPrice':35}, 'lowcost', self.file_path)
        stocks = F.find_good_stocks()
        self.stocks = [x[0] for x in stocks]
        print(self.stocks)

    def update_info(self):
        self.equity = self.my_trader.equity()
        self.owned_securities = self.my_trader.securities_owned()
        self.available_funds = self.my_trader.equity() - sum([x[1]*x[4] for x in self.my_trader.securities_owned()])

    def current_stock_info(self):
        self.open_log()
        try:
            table = []
            for s in self.owned_securities:
                datetime_format = datetime.strptime(s[2], '%Y-%m-%dT%H:%M:%S.%fZ')
                duration = datetime.now() - datetime_format
                table.append([s[0], round((s[4]/s[3]-1) * 100, 2), duration > timedelta(days=5), duration > timedelta(days=10)])
            table = sorted(table, key = lambda x: x[1])
            self.log.write(tabulate(table, headers = ['Stock', 'Total Gain/Loss', '> {} days', '> {} days'.format(self.sd, self.ld)]))
            self.log.write('\n')
        except Exception as e:
            self.log.write('Can\'t print table: unexpected error {}.\n'.format(e))
        self.close_log()

    def buy_stock(self, stock = None):
        self.open_log()
        self.log.write('\nBuying:\n')
        try:
            if stock == None:
                self.log.write('Nothing bought: no stock specified.\n')
            elif self.available_funds > self.buy_limit:
                last_price = float(self.my_trader.last_trade_price(stock))
                number_to_buy = int(self.buy_limit/last_price)
                self.my_trader.place_buy_order(self.my_trader.instruments(stock)[0], int(self.buy_limit/last_price))
                self.log.write('Buying {} stocks of {} at {} for a total of {}.\n'.format(number_to_buy, stock, last_price, last_price * number_to_buy))
                self.conn.execute('insert into history (id,date,activity,stock,gain) values (?, ?, ?, ?, ?)', (self.idCount, datetime.now(), 'BUY', stock, 'N/A'))
                self.idCount += 1
            else:
                self.log.write('Nothing bought: insufficient funds to buy stock. Need at least {} dollars.\n'.format(self.buy_limit))
        except Exception as e:
            self.log.write('Nothing bought: {}.\n'.format(e))
        self.close_log()

    def auto_buy_stocks(self):
        self.open_log()
        self.log.write('\nBuying:\n')
        try:
            if self.available_funds < self.buy_limit:
                self.log.write('Nothing bought: insufficient funds to buy stocks. Need at least {0} dollars.\n'.format(self.buy_limit))
            else:
                for i in range(int(self.available_funds / self.buy_limit)):
                    last_price = float(self.my_trader.last_trade_price(self.stocks[i]))
                    number_to_buy = int(self.buy_limit/last_price)
                    self.my_trader.place_buy_order(self.my_trader.instruments(self.stocks[i])[0], int(self.buy_limit/last_price))
                    self.log.write('Buying {} stocks of {} at {} for a total of {}.\n'.format(number_to_buy, self.stocks[i], last_price, last_price * number_to_buy))
                    self.conn.execute('insert into history (id,date,activity,stock,gain) values (?, ?, ?, ?, ?)', (self.idCount, datetime.now(), 'BUY', self.stocks[i], 'N/A'))
                    self.idCount += 1
                    time.sleep(10)
        #except Exception as e:
        except BufferError:
            self.log.write('Nothing bought: {}.\n'.format(e))
        self.close_log()

    def auto_sell_stocks(self):
        self.open_log()
        self.log.write('\nSelling:\n')
        try:
            for s in self.owned_securities:
                datetime_format = datetime.strptime(s[2], '%Y-%m-%dT%H:%M:%S.%fZ')
                duration = datetime.now() - datetime_format
                gain = round((s[4]/s[3]-1) * 100, 2)
                try:
                    if duration > timedelta(days=self.ld):
                        self.my_trader.place_sell_order(self.my_trader.instruments(s[0])[0], s[1])
                        self.log.write('Selling {}: More than {} days :|\n'.format(s[0], self.ld))
                        self.conn.execute('insert into history (id,date,activity,stock,gain) values (?, ?, ?, ?, ?)', (self.idCount, datetime.now(), 'SELL', s[0], gain))
                        self.idCount += 1
                    elif duration > timedelta(days=self.sd) and gain > 0:
                        self.my_trader.place_sell_order(self.my_trader.instruments(s[0])[0], s[1])
                        self.log.write('Selling {}: More than {} days and positive :)\n'.format(s[0], self.sd))
                        self.conn.execute('insert into history (id,date,activity,stock,gain) values (?, ?, ?, ?, ?)', (self.idCount, datetime.now(), 'SELL', s[0], gain))
                        self.idCount += 1
                    elif gain > 5:
                        self.my_trader.place_sell_order(self.my_trader.instruments(s[0])[0], s[1])
                        self.log.write('Selling {}: More than 5% :)\n'.format(s[0]))
                        self.conn.execute('insert into history (id,date,activity,stock,gain) values (?, ?, ?, ?, ?)', (self.idCount, datetime.now(), 'SELL', s[0], gain))
                        self.idCount += 1
                    elif gain < -5:
                        self.my_trader.place_sell_order(self.my_trader.instruments(s[0])[0], s[1])
                        self.log.write('Selling {}: Less than -5% :(\n'.format(s[0]))
                        self.conn.execute('insert into history (id,date,activity,stock,gain) values (?, ?, ?, ?, ?)', (self.idCount, datetime.now(), 'SELL', s[0], gain))
                        self.idCount += 1
                except Exception as e:
                    self.log.write('Couldn\'t sell {}: {}.\n'.format(s[0], e))
        except Exception as e:
            self.log.write('Nothing sold: {}.\n'.format(e))
        self.close_log()

    def new_log(self):
        # creates new log if different day
        if os.path.isfile('{}log{}.txt'.format(self.file_path,datetime.now().strftime('%y%m%d'))):
            pass
        else:
            self.log = open('{}log{}.txt'.format(self.file_path,datetime.now().strftime('%y%m%d')),'w')
            self.log.close()

    def open_log(self):
        self.log = open('{}log{}.txt'.format(self.file_path,datetime.now().strftime('%y%m%d')),'a')
        self.log.write('\n\nRobinhood Status: {}\n\n'.format(datetime.now()))

    def close_log(self):
        try:
            self.log.write('\nTook {} seconds.'.format(datetime.now() - self.start_time))
            self.log.close()
        except Exception as e:
            print('Couldn\'t close log: {}'.format(e))

    def printDB(self, db='log.db'):
        try:
            self.log.write('\nDatabase:')
            cur = sqlite3.connect(db).cursor()
            self.log.write('  '+str([header[0] for header in cur.execute("select * from history").description][1:]))
            for entry in cur.fetchall():
                self.log.write(entry)
            cur.close()
        except Exception as e:
            print('Couldn\'t print database: {}'.format(e))

    def send_email_AA(self):
        sendEmail(self.file_path, 'Robinhood Operation', ['takaomatt@gmail.com'],
                 ['blacklist.txt',self.file_path+'readme.txt',self.file_path+'log.db',
                 self.file_path+'.DS_Store', self.file_path+'log.db-journal'])


def autoSweep():
    r = Robinhood_AA()
    r.current_stock_info()
    r.auto_buy_stocks()
    r.auto_sell_stocks()
    r.printDB()
    r.send_email_AA()

def autoBuyOnly():
    r = Robinhood_AA()
    r.current_stock_info()
    r.auto_buy_stocks()
    r.send_email_AA()

def autoSellOnly():
    r = Robinhood_AA()
    r.current_stock_info()
    r.auto_sell_stocks()
    r.send_email_AA()

def statusOnly():
    r = Robinhood_AA()
    r.current_stock_info()
    r.send_email_AA()

def buyOneStock(stock):
    r = Robinhood_AA()
    r.current_stock_info()
    r.buy_stock(stock)
    #r.send_email_AA()

#
buyOneStock('CTRN')
