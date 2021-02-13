import backtrader as bt
from datetime import datetime
import glob
import os
from strategies import MomentumStrategy


cerebro = bt.Cerebro(stdstats=False)
cerebro.broker.set_coc(True)

spy = bt.feeds.BacktraderCSVData(dataname='./data/SPY/daily/SPY_daily_2001-02-05T060000_2021-02-05T060000',
                                 fromdate=datetime(2015,10,1),
                                 todate=datetime(2021,2,2),
                                 plot=True)
cerebro.adddata(spy)  # add S&P 500 Index
tickers = {'AAPL','AMZN','GOOG','TSLA','NVDA','DIS','KO','SQ','UBER','AMD','NIO','GM','PLTR'} #,'TWTR','PLUG','OPEN','CGC','PACB','MSTR'}


ftype = 'daily'
for ticker in tickers:
    # Load data
    list_of_files = glob.glob('./data/{}/{}/*'.format(ticker,ftype)) # get list of all data files for ticker
    latest_file = max(list_of_files, key=os.path.getctime)
    cerebro.adddata(bt.feeds.BacktraderCSVData(dataname=latest_file,
                                    fromdate=datetime(2016,2,2),
                                    todate=datetime(2021,2,2),
                                    plot=False))

cerebro.addobserver(bt.observers.Value)
cerebro.addanalyzer(bt.analyzers.SharpeRatio, riskfreerate=0.0)
cerebro.addanalyzer(bt.analyzers.Returns)
cerebro.addanalyzer(bt.analyzers.DrawDown)
cerebro.addstrategy(MomentumStrategy.MomentumStrategy)
results = cerebro.run()

cerebro.plot(iplot=False)[0][0]

print(f"Sharpe: {results[0].analyzers.sharperatio.get_analysis()['sharperatio']:.3f}")
print(f"Norm. Annual Return: {results[0].analyzers.returns.get_analysis()['rnorm100']:.2f}%")
print(f"Max Drawdown: {results[0].analyzers.drawdown.get_analysis()['max']['drawdown']:.2f}%")
