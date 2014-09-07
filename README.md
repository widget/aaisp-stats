AAISP stat display
=================

This is a program in Python3 that scrapes the AAISP billing pages available to customers and uses them to record stats about how much data has been uploaded and downloaded and generate some graphs.  As it is based on screen scraping it is vulnerable to AAISP changing their stat websites, and will probably not work for users with multiple lines or sites.

Its output is a single HTML file with SVGs embedded in the DOM.

Requirements
----------

This uses Python3 and the following dependencies (for 3!  not 2.x!):

* Beautiful Soup 4
* Requests
* Pygal

Install these with `pip3 install beautifulsoup4 requests pygal`.  If using a newish Linux distribution you will find pip available separately (below Python 3.4 at any rate) and the requests library is typically available as a dedicated package (e.g. `python3-requests`).

Usage
-----

Know your username and password for the AAISP billing website (clueless).  Write it to a file in the form

        ["username", "password"]

Protect this file with a suitable umask as it has your credentials in plaintext.  Run the `scrape_usage.py` program and pass this file in with the --creds argument.  Use --fetch to grab available stats and store them in the local directory.  Use --graph to create an output HTML file, and use --output to direct where this file is put.  Both --fetch and --graph can be used in a single invocation.

I then place the HTML on an internal webserver to look at.

Command line output:

	usage: scrape_usage.py [-h] [--creds CREDS] [-f] [-g] [-o OUTPUT]

	Fetch/parse AAISP usage data

	optional arguments:
	-h, --help            show this help message and exit
	--creds CREDS         Location of the credentials with which to log into
							clueless
	-f, --fetch           Fetch latest data from clueless and store to disc
							(requires creds)
	-g, --graph           Generate HTML output
	-o OUTPUT, --output OUTPUT
							Location of HTML output


TODO
----

* Find a better way to store the credentials and still be able to non-interactively decrypt them
* Make the stat graphs better