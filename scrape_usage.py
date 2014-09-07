#!/usr/bin/python3

"""
Fetching data from AAISP's human-readable usage stats, parsing it, and generating vector graph output.
"""


import argparse
from bs4 import BeautifulSoup
import calendar
from collections import namedtuple
import datetime
import json
import pickle
import pygal
import re
import requests
import sys
import time

MonthlyUsage = namedtuple("MonthlyUsage", ["month", "peak_down", "peak_up", "other_down", "other_up", "uptime"])
BillingBasic = namedtuple("BillingBasic", ["start", "end", "bf", "used", "allowance", "topup", "details"])
Usage = namedtuple("Usage", ["start", "duration","peak_down", "peak_up", "other_down", "other_up"])


def convertWithPrefix(text):
	if text == "":
		return 0.0
	num = float(text[:-1])
	if text.endswith('M'):
		num = num / 1024
	return num


def parseMonthlyUsageRow(row):
	cells = row.find_all(True)
	month = cells[0].text
	pd = convertWithPrefix(cells[1].text)
	pu = convertWithPrefix(cells[2].text)
	od = convertWithPrefix(cells[3].text)
	ou = convertWithPrefix(cells[4].text)
	up = float(cells[5].text[:-1]) # cut the percentage
	return MonthlyUsage(month, pd, pu, od, ou, up)


def parseDailyUsageRow(row):
	cells = row.find_all('td')
	try:
		st = datetime.datetime.strptime(row.find('th').text, "%a %d %b %Y") 
		tu = convertWithPrefix(cells[0].text)
		td = convertWithPrefix(cells[1].text)
		pu = convertWithPrefix(cells[2].text)
		pd = convertWithPrefix(cells[3].text)
		ou = tu - pu
		od = td - pd
		return Usage(st,#datetime.datetime.fromtimestamp(time.mktime(st)),
			   datetime.timedelta(days=1),
					pd, pu, od, ou)
	except ValueError:
		return None
	

def parseHourlyUsageRow(row, up=False):
	cells = row.find_all('td')
	try:
		start_cell=row.find('th')
		start_time = datetime.datetime.strptime(start_cell.text, "%a %d %b %Y")
		#start_time = datetime.datetime.fromtimestamp(time.mktime(st))
		peakday = 'W' in start_cell["class"]
		ret = []
		for c in cells:
			amt = convertWithPrefix(c.text)
			hr = int(c["class"][0][1:])
			if peakday:
				peak = 9 <= hr <= 17
			else:
				peak = False
				
			if peak:
				if up:
					u = Usage(start_time + datetime.timedelta(hours=hr), 
								datetime.timedelta(hours=1),
								0, amt, 0, 0)
				else:
					u = Usage(start_time + datetime.timedelta(hours=hr), 
								datetime.timedelta(hours=1),
								amt, 0, 0, 0)
			else:
				if up:
					u = Usage(start_time + datetime.timedelta(hours=hr), 
								datetime.timedelta(hours=1),
								0, 0, 0, amt)
				else:
					u = Usage(start_time + datetime.timedelta(hours=hr), 
								datetime.timedelta(hours=1),
								0, 0, amt, 0)
			ret.append(u)
		return ret
	except ValueError:
		raise


def parseBillingBasicRow(row):
	cells = row.find_all(True)
	start = cells[0].text
	end = cells[1].text
	bf = float(cells[3].text)
	used = float(cells[4].text)
	allow = float(cells[5].text)
	topup = 0.0
	if cells[6].text:
		topup = float(cells[6].text)
	link = cells[8].a.get('href')
	return BillingBasic(start, end, bf, used, allow, topup, link)


CLUELESS="https://clueless.aa.net.uk/"


def fetchData(creds):
	session = requests.Session()
	session.auth = tuple(creds)
	params = { "LINE" : "1",
			"LIMIT" : "31",
			"LOGIN" : creds[0]
			}
	r = session.get(CLUELESS + 'usage.cgi', params=params)

	assert r.status_code == 200

	decoded_main = BeautifulSoup(r.text)

	table_list = decoded_main.find_all('table')

	monthly_usage = table_list[-4]
	billing = table_list[-3]
	daily_usage = table_list[-2]
	hourly_usage = table_list[-1]

	assert "Month" in monthly_usage.text
	assert "Period" in billing.text
	
	match=re.compile(r"OE[01]")
	rows = monthly_usage.find_all('tr', class_=match)
	usages_mon = [parseMonthlyUsageRow(c) for c in rows]
	rows = billing.find_all('tr', class_=match)
	billbasic = [parseBillingBasicRow(c) for c in rows]
	
	rows = daily_usage.find_all('tr', class_=match)
	usages_day = [parseDailyUsageRow(c) for c in rows]
	rows = hourly_usage.find_all('tr', class_=match)
	assert not len(rows) % 2
	half = int(len(rows)/2)
	
	usages_hour = [parseHourlyUsageRow(c) for c in rows[:half]] + [parseHourlyUsageRow(c, True) for c in rows[half:]]
	
	return {"month" : usages_mon, "day" : usages_day, "hour" : usages_hour}, billbasic


if __name__ == "__main__":
	
	parser = argparse.ArgumentParser(description="Fetch/parse AAISP usage data")
	parser.add_argument("--creds", help="Location of the credentials with which to log into clueless")
	parser.add_argument("-f", "--fetch", default=False, action="store_const", const=True,
					 help="Fetch latest data from clueless and store to disc (requires creds)")
	parser.add_argument("-g", "--graph", default=False, action="store_const", const=True,
					 help="Generate HTML output")
	parser.add_argument("-o", "--output", default="./output.html",
					 help="Location of HTML output")
	
	args = parser.parse_args()
	
	if args.fetch:
		print("Fetching latest data")
		if not args.creds:
			print("Credentials in JSON format required for fetching data")
			sys.exit(1)
		creds = json.load(open(args.creds, "r"))
		u, b = fetchData(creds)
		pickle.dump(u, open("usages.bin","wb"))
		pickle.dump(b, open("billing.bin","wb"))
		
	if args.graph:
		usages = pickle.load(open("usages.bin", "rb"))
		billing = pickle.load(open("billing.bin", "rb"))
	
		this_mon = billing[0]
		
		cal = calendar.Calendar()
		today = datetime.date.today()
		days_in_period = [x for x in cal.itermonthdays(today.year, today.month) if x > 0]
		passed = [x for x in days_in_period if x < today.day]
		to_come = [x for x in days_in_period if x not in passed]
		bill_ratio = float(len(passed))/float(len(days_in_period))
	
		forecast = 0.0
		if bill_ratio > 0.0:
			forecast = this_mon.used / bill_ratio
	
		our_text = "At this rate we will take %.2f units into next month" % -(this_mon.bf+forecast-this_mon.allowance)
		over = False
		if this_mon.used > this_mon.allowance:
			our_text = "We are ALREADY using more data than we buy each month!"
			over = True
		elif forecast > this_mon.allowance:
			our_text = "We are forecast to use more data than we buy each month"
		
		from pygal.style import LightenStyle, LightColorizedStyle
		ourstyle = LightenStyle('#235670', step=5, base_style=LightColorizedStyle)
		ourstyle.background = '#ffffff'
		
		conf = pygal.Config()
		conf.style = ourstyle
		conf.legend_at_bottom = True
		
		usage_pie = pygal.Pie(conf)
		usage_pie.title = "Current monthly usage (units)"
		if over:
			usage_pie.add("Over-usage", this_mon.used - this_mon.allowance)
			usage_pie.add("Allowance", this_mon.allowance)
		else:
			usage_pie.add("Usage", this_mon.used)
			usage_pie.add("Remaining", this_mon.allowance - this_mon.bf)
		
		pop = pygal.Pie(conf)
		pop.title = "Peak/off-peak (units)"
		pop.add("Peak", usages["month"][0].peak_down / 2.5)
		pop.add("Off-peak", usages["month"][0].other_down / 50)
	
		time_cht = pygal.HorizontalStackedBar(conf, show_y_labels=False, height=120, width=800)
		time_cht.title = "Distance through billing period"
		time_cht.x_labels_major_every = 7
		time_cht.x_labels_minor_every = 1
		time_cht.add("Elapsed", len(passed))
		time_cht.add("Remaining", len(to_come))
		
		billing.reverse()
		bf_chrt = pygal.Line(conf, interpolate="cubic", height=400, width=800)
		bf_chrt.title = "Monthly usage (units)"
		bf_chrt.y_title = "Units"
		bf_chrt.x_labels = [b.start for b in billing]
		bf_chrt.add("Accrued", [-b.bf for b in billing])
		bf_chrt.add("Used", [b.used for b in billing])
		bf_chrt.add("Allowance", [b.allowance for b in billing])
		
		usages_mon = usages["month"]
		usages_mon.reverse()
		
		usage_mon_chrt = pygal.StackedLine(conf, logarithmic=True,
									 x_label_rotation=45, fill=True,
									 interpolate="cubic")
		usage_mon_chrt.title = "Monthly usage (GB)"
		#usage_mon_chrt.y_title = "Data"
		usage_mon_chrt.x_labels = [u.month for u in usages_mon]
		usage_mon_chrt.add("Peak upload", [u.peak_up for u in usages_mon])
		usage_mon_chrt.add("Peak download",[u.peak_down for u in usages_mon])
		usage_mon_chrt.add("Non-peak upload", [u.other_up for u in usages_mon])
		usage_mon_chrt.add("Non-peak download", [u.other_down for u in usages_mon])
		
		day = [d for d in usages["day"] if d is not None]
		day.reverse()
		usage_day_chrt = pygal.StackedLine(conf, x_label_rotation=45, interpolate="hermite",
											height=400, width=800)
		usage_day_chrt.x_labels = [d.start.strftime("%a %d %b") for d in day]
		usage_day_chrt.title = "Daily usage (GB)"
		usage_day_chrt.add("Peak", [d.peak_down for d in day])
		usage_day_chrt.add("Non-peak", [d.other_down for d in day])
		
		doc = """<html xmlns="http://www.w3.org/1999/xhtml">
		<head>
		<meta charset="UTF-8"/>
		<title>Our usage</title>
		<style>
		p.title {
			font-size:300%;
			text-align: center;
			font-family: monospace;
		}
		p.text-summary {
			font-family: sans-serif;
			margin-top=2em;
			margin-bottom=2em;
			margin-left=10%;
			margin-right=10%;
			font-size: 150%;
		}
		table#summary {
			width:50%; 
			margin-left:25%; 
			margin-right:25%;
			border-spacing: 1em;
			font-size: 200%;
		}
		#summary th {
			font-family: sans-serif;
			text-align: left;
			margin=5em;
		}
		#summary td {
			font-family: sans-serif;
			text-align: right;
			margin=5em;
			
		}
		ul
		{
			list-style-type: none;
			padding:0; margin:0;
		}
		li.horiz
		{
			display:table-cell; 
			padding: 1px;
			width: 500px;
		}
		</style>
		<script>
		function resizeMe() {
			var elements = document.querySelectorAll('li.horiz');
			for(var i = 0; i < elements.length; i++) {
				elements[i].style.width = (screen.width/2) - 20 + "px";
			}
		}
		</script>
		</head>
		<body onload="resizeMe()">
		<p class="title">Broadband usage</p>
		""" + """<p class="text-summary">{summary}</p>
		<table id="summary">
		<tbody>
		<tr><th class="summary-title">Brought forward</th><td>{this_mon.bf:.3}</td></tr>
		<tr><th class="summary-title">Allowance</th><td>{this_mon.allowance:.3}</td></tr>
		<tr><th class="summary-title">Usage so far</th><td>{this_mon.used:.3}</td></tr>
		<tr><th class="summary-title">Forecast</th><td>{fcast:.3}</td></tr>
		<tr><th class="summary-title">Remaining</th><td>{this_rem:.3}</td></tr>
		</tbody>
		</table>
		
		<ul>
		<li>{time_chart}</li>
		<ul>
		<li class="horiz">{usage_chart}</li>
		<li class="horiz">{pop_chart}</li>		
		</ul>
		<li>{backfill_chart}</li>
		<li>{usage_mon_chart}</li>
		<li>{usage_day_chart}</li>
		</ul>
		<p>Generated: {now}</p>
		</body>
		</html>""".format(summary=our_text, this_mon=this_mon, fcast=forecast,
				   this_rem=(this_mon.allowance - this_mon.bf)-this_mon.used,
						backfill_chart=bf_chrt.render(disable_xml_declaration=True),
						time_chart=time_cht.render(disable_xml_declaration=True), 
						usage_chart=usage_pie.render(disable_xml_declaration=True),
						usage_mon_chart=usage_mon_chrt.render(disable_xml_declaration=True),
						usage_day_chart=usage_day_chrt.render(disable_xml_declaration=True),
						pop_chart=pop.render(disable_xml_declaration=True),
						now=datetime.datetime.now().ctime()
						)
		
		with open(args.output, "w") as html:
			html.write(doc)

