#!/usr/bin/python3

import argparse
import requests
from bs4 import BeautifulSoup
import re
from collections import namedtuple
import json
import pygal
import calendar
from datetime import date
import sys

MonthlyUsage = namedtuple("MonthlyUsage", ["month", "peak_down", "peak_up", "other_down", "other_up", "uptime"])
BillingBasic = namedtuple("BillingBasic", ["start", "end", "bf", "used", "allowance", "topup", "details"])


def convertWithPrefix(text):
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
	params = { "LINE" : "",
			"LOGIN" : creds[0]
			}
	r = session.get(CLUELESS + 'usage.cgi', params=params)

	assert r.status_code == 200

	decoded_main = BeautifulSoup(r.text)

	table_list = decoded_main.find_all('table')

	monthly_usage = table_list[-4]
	billing = table_list[-3]

	assert "Month" in monthly_usage.text
	assert "Period" in billing.text
	
	match=re.compile(r"OE[01]")
	rows = monthly_usage.find_all('tr', class_=match)
	usages = [parseMonthlyUsageRow(c) for c in rows]
	rows = billing.find_all('tr', class_=match)
	billbasic = [parseBillingBasicRow(c) for c in rows]
	
	return usages, billbasic


if __name__ == "__main__":
	
	parser = argparse.ArgumentParser(description="Fetch/parse AAISP usage data")
	parser.add_argument("--creds")
	parser.add_argument("-f", "--fetch", default=False, action="store_const", const=True)
	parser.add_argument("-g", "--graph", default=False, action="store_const", const=True)
	parser.add_argument("-o", "--output", default="./output.html")
	
	args = parser.parse_args()
	
	if args.fetch:
		print("Fetching latest data")
		if not args.creds:
			print("Credentials in JSON format required for fetching data")
			sys.exit(1)
		creds = json.load(open(args.creds, "r"))
		u, b = fetchData(creds)
		json.dump(u, open("usages.json","w"))
		json.dump(b, open("billing.json","w"))
		
	if args.graph:
		u = json.load(open("usages.json"))
		b = json.load(open("billing.json"))

		usages = [MonthlyUsage(*obj) for obj in u]
		billing = [BillingBasic(*obj) for obj in b]
	
		this_mon = billing[0]
		
		cal = calendar.Calendar()
		days_in_period = [x for x in cal.itermonthdays(date.today().year, date.today().month) if x > 0]
		passed = [x for x in days_in_period if x < date.today().day]
		to_come = [x for x in days_in_period if x not in passed]
		bill_ratio = float(len(passed))/float(len(days_in_period))
		forecast = this_mon.used / bill_ratio
	
		our_text = "At this rate we will take %.2f units into next month" % -(this_mon.bf+forecast-this_mon.allowance)
		over = False
		if this_mon.used > this_mon.allowance:
			our_text = "We are ALREADY using more data than we buy each month!"
			over = True
		elif forecast > this_mon.allowance:
			our_text = "We are forecast to use more data than we buy each month"
		
		from pygal.style import RedBlueStyle
		ourstyle = RedBlueStyle
		
		usage_pie = pygal.Pie(style=ourstyle)
		usage_pie.title = "Current monthly usage"
		if over:
			usage_pie.add("Over-usage", this_mon.used - this_mon.allowance)
			usage_pie.add("Allowance", this_mon.allowance)
		else:
			usage_pie.add("Usage", this_mon.used)
			usage_pie.add("Remaining", this_mon.allowance - this_mon.bf)
		
	
		time_cht = pygal.HorizontalStackedBar(style=ourstyle, show_y_labels=False, height=120, width=800)
		time_cht.title = "Distance through billing period"
		time_cht.x_labels_major_every = 7
		time_cht.x_labels_minor_every = 1
		time_cht.add("Elapsed", len(passed))
		time_cht.add("Remaining", len(to_come))
		
		billing.reverse()
		bf_chrt = pygal.Line(style=ourstyle, interpolate="cubic", height=400, width=800)
		bf_chrt.title = "Historic usage"
		bf_chrt.y_title = "Units"
		bf_chrt.x_labels = [b.start for b in billing]
		bf_chrt.add("Accrued", [-b.bf for b in billing])
		bf_chrt.add("Used", [b.used for b in billing])
		bf_chrt.add("Allowance", [b.allowance for b in billing])
		
		doc = """<html><title>Our usage</title>
		<style>
		p.title {
			font-size:200%;
			text-align: center;
			font-family: monospace;
		}
		p.text-summary {
			font-family: sans-serif;
			margin-top=2em;
			margin-bottom=2em;
			margin-left=10%;
			margin-right=10%;
		}
		table#summary {
			width:50%; 
			margin-left:25%; 
			margin-right:25%;
			border-spacing: 1em;
			font-size: 110%;
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
		</style>
		<body>
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
		<p>{usage_chart}</p>
		<p>{time_chart}</p>
		<p>{backfill_chart}</p>
		</body>
		</html""".format(summary=our_text, this_mon=this_mon, fcast=forecast,
				   this_rem=(this_mon.allowance - this_mon.bf)-this_mon.used,
						backfill_chart=bf_chrt.render(disable_xml_declaration=True),
						time_chart=time_cht.render(disable_xml_declaration=True), 
						usage_chart=usage_pie.render(disable_xml_declaration=True))
		
		with open(args.output, "w") as html:
			html.write(doc)

