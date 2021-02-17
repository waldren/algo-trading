
'''
Original code and algo from: https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/
Revised code from: https://www.backtrader.com/blog/2019-05-20-momentum-strategy/momentum-strategy/

Changes:
 - Monmentum func change <this_array> to <period>  and added variable for indicator 
    that is passed to function call
 - In __init__ 
    - fixed typo (add <p>) on call to params <momentum_period>
    - added:  self.stock_under_idx_mav_filter
        - but this does not work, so reverted back a checks in rebalance and reposition method
 - In <prenext> added: >= self.p.stock_period 
 - In <prenext> and <nextstart> changed <self.datas> to <self.stocks> to exclude the idx datafeed
 - Fixed bugs in selling stocks as it checked self.data for positions not d
 - Added timers for rebalance and reposition
 - Converted top percentage of stocks to buy to a param
 - Converted risk parity sizing to a param

TODO 
    * Add a cross over indicator for the SPY < SMA check

'''
import backtrader as bt
import numpy as np
from scipy.stats import linregress
import collections
import logging

mod_log = logging.getLogger(__name__)

class RepositionTimer(object):
    def __init__(self):
        self.fridays = 0
        self.curmonth = -1

    def __call__(self, d):
        _, _, isowkday = d.isocalendar()

        if d.month != self.curmonth:
            self.curmonth = d.month
            self.fridays = 0

        # Mon=1 ... Sun=7
        if isowkday == 5:
            self.fridays += 1

            if self.fridays == 2:  # 2nd Friday
                return True  # timer allowed

        return False  # timer disallowed

def momentum_func(ind, period):
    if (len(period) != 90):
        mod_log.debug("Period Length: {}".format(len(period)))
    r = np.log(period)
    slope, _, rvalue, _, _ = linregress(np.arange(len(r)), r)
    annualized = (1 + slope) ** 252
    res = annualized * (rvalue ** 2)
   # mod_log.debug("Res: {}".format(res))
    return res


class MomentumIndicator(bt.ind.OperationN):
    lines = ('trend',)
    params = dict(period=50)
    func = momentum_func

class MomentumStrategy(bt.Strategy):
    params = dict(
        momentum=MomentumIndicator,  # parametrize the momentum and its period
        momentum_period=90,

        movav=bt.ind.SMA,  # parametrize the moving average and its periods
        idx_period=200,
        stock_period=100,

        volatr=bt.ind.ATR,  # parametrize the volatility and its period
        vol_period=20,

        buy_top_perc_stock=0.3,  # the fraction of the top momentum stocks to buy
        risk_parity_size=0.001,  # a standard weight to size the position in stocks
        rebal_weekday=5  # rebalance 5 is Friday
    )

    def debug_stocks(self, stocklist):
        for d in stocklist:
            mod_log.debug(" {} in stocklist".format(d.p.dataname))

    def __init__(self):
        self.log = logging.getLogger(__name__)

        #self.i = 0  # See below as to why the counter is commented out
        self.inds = collections.defaultdict(dict)  # avoid per data dct in for

        # Use "self.data0" (or self.data) in the script to make the naming not
        # fixed on this being a "spy" strategy. Keep things generic
        # self.spy = self.datas[0]
        # self.stocks = self.datas[1:]
        # Only add datafeeds with adequate length
        stocks_to_add = []
        for d in self.datas[1:]:
            if (len(d.array) > self.p.momentum_period):
                stocks_to_add.append(d)
            else:
                self.log.debug("Remove short stock datafeed: {} with len {}".format(d.p.dataname, len(d.array)))
        self.stocks = stocks_to_add
        self.log.debug("{} total stocks".format(len(self.stocks)))
        self.debug_stocks(self.stocks)

        # Again ... remove the name "spy"
        self.idx_mav = self.p.movav(self.data0, period=self.p.idx_period)
        stocks_too_short = []
        for i, d in enumerate(self.stocks):            
            self.log.debug("(i={}) Processing Datafeed: {} with len {}".format(i, d.p.dataname, len(d.array)))
            self.inds[d]['mom'] = self.p.momentum(d, period=self.p.momentum_period)
            self.inds[d]['mav'] = self.p.movav(d, period=self.p.stock_period)
            self.inds[d]['vol'] = self.p.volatr(d, period=self.p.vol_period)
        
        # Timer to support rebalancing weekcarry over in case of holiday
        self.add_timer(
            name = "rebalance",
            when=bt.Timer.SESSION_START,
            weekdays=[self.p.rebal_weekday],
            weekcarry=True,  # if a day isn't there, execute on the next
        )
        self.add_timer(
            name = "reposition",
            when=bt.Timer.SESSION_START,
            allow=RepositionTimer(),
            weekcarry=True,  # if a day isn't there, execute on the next
        )
        #List of stocks that have sufficient length (based on indicators)
        self.d_with_len = []
    
    def notify_timer(self, timer, when, *args, **kwargs):
        if kwargs['name'] == 'rebalance':
            self.log.debug("Rebalanceing at {}".format(when))
            self.rebalance_portfolio()
        elif kwargs['name'] == 'reposition':
            self.log.debug("Repositioning at {}".format(when))
            self.rebalance_positions()
        else:
            self.log.debug("Unknown Timer at {}".format(when))

    def prenext(self):
        # Populate d_with_len
        self.d_with_len = [d for d in self.stocks if len(d) >= self.p.stock_period]
        self.log.debug("[prenext] Stocks with length: {}".format(len(self.d_with_len)))
        # call next() even when data is not available for all tickers
        self.next()

    def nextstart(self):
        # This is called exactly ONCE, when next is 1st called and defaults to
        # call `next`
        self.log.debug("[nextstart] Setting All Stock to stocks with appropriate lenght")
        self.d_with_len = self.stocks  # all data sets fulfill the guarantees now

        self.next()  # delegate the work to next

    def next(self):
        self.log.debug("Next")
        # converted code to use timers
        '''
        l = len(self)
         if l % 5 == 0:
             self.rebalance_portfolio()
        if l % 10 == 0:
            self.rebalance_positions()
        '''
    
    def rebalance_portfolio(self):
        # only look at data that we can have indicators for 
        self.rankings = self.d_with_len
        self.log.debug("[rebalance_portfolio] Rankings Length: {}".format(len(self.rankings)))
        #if no stocks are ready return   - Added but not sure if needed
        if(len(self.rankings) == 0):
            return

        self.rankings.sort(key=lambda d: self.inds[d]["mom"][0])
        num_stocks = len(self.rankings)
        
        # sell stocks based on criteria
        for i, d in enumerate(self.rankings):
            if self.getposition(d).size:  # changed self.data to d
                if i > num_stocks * self.p.buy_top_perc_stock or d < self.inds[d]["mav"]:
                    self.close(d)
        
        if self.datas[0].open < self.idx_mav:  #self.stock_under_idx_mav_filter:
            return
        
        # buy stocks with remaining cash
        for i, d in enumerate(self.rankings[:int(num_stocks * self.p.buy_top_perc_stock)]):
            cash = self.broker.get_cash()
            value = self.broker.get_value()
            if cash <= 0:
                break
            if not self.getposition(d).size:   # changed self.data to d
                size = value * self.p.risk_parity_size / self.inds[d]["vol"]
                self.buy(d, size=size)
                
        
    def rebalance_positions(self):
        num_stocks = len(self.rankings)
        
        if self.datas[0].open < self.idx_mav:      #self.stock_under_idx_mav_filter:
            return

        # rebalance all stocks
        for i, d in enumerate(self.rankings[:int(num_stocks * self.p.buy_top_perc_stock)]):
            cash = self.broker.get_cash()
            value = self.broker.get_value()
            if cash <= 0:
                break
            size = value * self.p.risk_parity_size  / self.inds[d]["vol"]
            self.order_target_size(d, size)