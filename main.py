#!/usr/bin/env python

'''
 Analyzer for iPhone backup made by Apple iTunes

 (C)opyright 2011 Mario Piccinelli <mario.piccinelli@gmail.com>
 Released under MIT licence
 
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:

 The above copyright notice and this permission notice shall be included in
 all copies or substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 THE SOFTWARE.

'''

# GENERIC IMPORTS --------------------------------------------------------------------------------------

# sqlite3 support library
import sqlite3
# system libraries
import sys, os
# graphic libraries
from Tkinter import *
import Tkinter, ttk
import tkFileDialog, tkMessageBox
# datetime used to convert unix timestamps
from datetime import datetime
# hashlib used to build md5s ans sha1s of files
import hashlib
# binascci used to try to convert binary data in ASCII
import binascii
# getopt used to parse command line options
import getopt
# time used to read system date and time of files
import time
# Python Image Library: graphics and EXIF data from JPG images
from PIL import Image, ImageTk
from PIL.ExifTags import TAGS
# String IO to pass data dumps from databases directly to PIL
import StringIO	
# decode base64 encoded text
import base64
# string functions
import string
# to open external file viewers
import subprocess

# APPLICATION FILES IMPORTS -------------------------------------------------------------------------

# magic.py - identify file type using magic numbers
import magic
# mbdbdecoding.py - functions to decode iPhone backup manifest files
import mbdbdecoding
# decodeManifestPlist.py - functions to decode Manifest.plist file
import decodeManifestPlist

# GLOBALS -------------------------------------------------------------------------------------------

# version
version = "1.2"
creation_date = "Oct. 2011"

# set this path from command line
backup_path = "Backup2/" 

# saves references to images in textarea
# (to keep them alive after callback end)
photoImages = []

# limits the display of rows dumped from a table
rowsoffset = 0
rowsnumber = 100

# set SMALLMONITOR to 1 to modify main UI for small monitors
# (such as a 7' Asus eeepc)
smallmonitor = 0

# global font configuration
normalglobalfont = ('Times', 12, 'normal')
smallglobalfont = ('Times', 8, 'normal')
globalfont=normalglobalfont

# iOS version
# 4 - iOS 4
# 5 - iOS 5
#   - does not decode manifest.mbdx (which doesn't exist anymore)
#   - instead find real file name by SHA1ing the string "domain-filename"  
iOSVersion = 5

# FUNCTIONS -------------------------------------------------------------------------------------------

def substWith(text, subst = "-"):
	if (len(text) == 0):
		return subst
	else:
		return text

def autoscroll(sbar, first, last):
    """Hide and show scrollbar as needed."""
    first, last = float(first), float(last)
    if first <= 0 and last >= 1:
        sbar.grid_remove()
    else:
        sbar.grid()
    sbar.set(first, last)
	
def md5(md5fileName, excludeLine="", includeLine=""):
	"""Compute md5 hash of the specified file"""
	m = hashlib.md5()
	try:
		fd = open(md5fileName,"rb")
	except IOError:
		return "<none>"
	content = fd.readlines()
	fd.close()
	for eachLine in content:
		if excludeLine and eachLine.startswith(excludeLine):
			continue
		m.update(eachLine)
	m.update(includeLine)
	return m.hexdigest()

FILTER=''.join([(len(repr(chr(x)))==3) and chr(x) or '.' for x in range(256)])

def dump(src, length=8, limit=10000):
	N=0; result=''
	while src:
		s,src = src[:length],src[length:]
		hexa = ' '.join(["%02X"%ord(x) for x in s])
		s = s.translate(FILTER)
		result += "%04X   %-*s   %s\n" % (N, length*3, hexa, s)
		N+=length
		if (len(result) > limit):
			src = "";
			result += "(analysis limit reached after %i bytes)"%limit
	return result

def hex2string(src, length=8):
	N=0; result=''
	while src:
		s,src = src[:length],src[length:]
		hexa = ' '.join(["%02X"%ord(x) for x in s])
		s = s.translate(FILTER)
		N+=length
		result += s
	return result	

def hex2nums(src, length=8):
    N=0; result=''
    while src:
       s,src = src[:length],src[length:]
       hexa = ' '.join(["%02X"%ord(x) for x in s])
       s = s.translate(FILTER)
       N+=length
       result += (hexa + " ")
    return result
    
def log(text):
	logbox.insert(END, "\n%s"%text)
	logbox.yview(END)
	
def maintext(text):
	textarea.insert(END, "%s"%text)

def clearmaintext():
	textarea.delete(1.0, END)
	
# scans the main tree view and returns the code of the node with a specified ID
# (by the way, the ID is the index of the element in the index database)
def searchIndexInTree(index, parent=""):
	#print("---- searching under node: %s"%(tree.item(parent)['text']))
	for node in tree.get_children(parent):			
		#print("node under exam: %s - %s"%(node,tree.item(node)['text']))
		id = tree.set(node, "id")
		#print("Confronto id %s con %s"%(id, index))
		if (id != ""):
			if (int(id) == int(index)): 
				#print("found!")
				return node			
		sottonodi = searchIndexInTree(index, node)
		if (sottonodi != None): return sottonodi	
	return
	
# returns the real file name for the searched element
def realFileName(filename="", domaintype=""):
	query = "SELECT fileid FROM indice WHERE 1=1"
	if (filename != ""):
		query = query + " AND file_name = \"%s\""%filename
	if (domaintype != ""):
		query = query + " AND domain_type = \"%s\""%domaintype

	cursor.execute(query);
	results = cursor.fetchall()
			
	if (len(results) > 0):
		return results[0][0]
	else:
		return ""	
	
# Called when a button is clicked in the buttonbox (upper right) -----------------------------------------

# open selected file in OS viewer
fileNameForViewer = ""
def openFile(event):
	global fileNameForViewer
	
	if (len(fileNameForViewer) > 0):
	
		answer = tkMessageBox.askyesno("Caution", "Are you sure you want to open the selected file with an external viewer? This could modify the evidence!", icon="warning", default="no")

		if (answer):
			print("Opening with viewer: %s"%fileNameForViewer)
			
			# mac os specific
			if sys.platform.startswith('darwin'):
				log("Opening with Mac Os \"open\" the file: %s"%(fileNameForViewer))
				subprocess.call(['open', fileNameForViewer], shell=False)
			
			# linux specific
			elif sys.platform.startswith('linux'):
				log("Opening with Linux \"gnome-open\" the file: %s"%(fileNameForViewer))
				subprocess.call(['gnome-open', fileNameForViewer], shell=False)
			
			# windows specific
			elif sys.platform.startswith('win'):
				log("Opening with Windows \"start\" the file: %s"%(fileNameForViewer))
				subprocess.call(['start', fileNameForViewer])
			
			# other
			else:
				log("This platform doesn't support this function.")

# search function globals
pattern = ""
searchindex = "1.0"

def buttonBoxPress(event):		
	
	# SEARCH button
	
	if (event.widget['text'] == "Search"):
		
		global pattern
		global searchindex
		
		if (pattern != searchbox.get(1.0, END).strip() or searchindex == ""):
			searchindex = "1.0";
		
		pattern = searchbox.get("1.0", END).strip()
		if (len(str(pattern)) == 0): return
		
		textarea.mark_set("searchLimit", textarea.index("end"))
		
		searchindex = textarea.search("%s"%pattern, "%s+1c"%(searchindex) , "searchLimit", regexp = True, nocase = True)
		if (searchindex == ""): return
		
		textarea.tag_delete("yellow")
		textarea.tag_configure("yellow",background="#FFFF00")
		textarea.tag_add("yellow", searchindex, "%s+%sc"%(searchindex, str(len(pattern))))
		
		textarea.mark_set("current", searchindex)
		textarea.yview(searchindex)
	
# WRITE TEXT TO FILE button

def writeTXT(): 

	outfile = tkFileDialog.asksaveasfile(mode='w', parent=root, initialdir='/home/', title='Select output text file')
	if (outfile):
		text = textarea.get("1.0", END)
		outfile.write(text)
		tkMessageBox.showwarning("Done", "Text saved\n")
		outfile.close()
	else:
		tkMessageBox.showwarning("Error", "Text NOT saved\n")


# Called when the "convert from unix timestamp" button is clicked  ------------------------------------

def convertTimeStamp(event):
	timestamp = timebox.get("1.0", END)
	if (timestamp.strip() == ""): return
	
	try:
		timestamp = int(timestamp)
	except:
		timebox.config(background="IndianRed1")
		return
	
	timestamp = timestamp + 978307200 #JAN 1 1970
	convtimestamp = datetime.fromtimestamp(int(timestamp))
	timebox.delete("1.0", END)
	timebox.insert("1.0", convtimestamp)

def clearTimeBox(event):
	timebox.config(background="white")
	
# MAIN ----------------------------------------------------------------------------------------------------

if __name__ == '__main__':

	def banner():
		print("\niPBA - iPhone backup analyzer v. %s (%s)"%(version, creation_date))
		print("Released by <mario.piccinelli@gmail.com> under MIT licence")

	# usage
	def usage():
		banner()
		print("")
		print(" -h              : this help")
		print(" -d <dir>        : backup dir")
		print(" -s              : adapt main UI for small monitors (such as 7')")
		print(" -4              : iOS 4 backup data (default is iOS 5)")

	# input parameters
	try:
		opts, args = getopt.getopt(sys.argv[1:], "hd:s4")
	except getopt.GetoptError as err:
		usage()
		print("\n%s\n"%str(err))
		sys.exit(2)
	
	for o, a in opts:
		if o in ("-h"):
			usage()
			sys.exit(0)
		
		if o in ("-d"):
			backup_path = a
			if (backup_path.strip()[-1] != "/"):
				backup_path = backup_path + "/"
		
		if o in ("-s"):
			smallmonitor = 1
			globalfont=smallglobalfont
		
		if o in ("-4"):
			iOSVersion = 4

	# chech existence of backup dir
	if (not os.path.isdir(backup_path)):
		usage()
		print("\nThe provided backup dir \"%s\" is not a valid folder.\n"%backup_path)
		sys.exit(1)

	# decode Manifest files
	mbdbPath = backup_path + "Manifest.mbdb"
	if (os.path.exists(mbdbPath)):
		mbdb = mbdbdecoding.process_mbdb_file(mbdbPath)
	else:
		usage()
		print("\nManifest.mbdb not found in path \"%s\". Are you sure this is a correct iOS backup dir?\n"%(backup_path))
		sys.exit(1)
	
	# decode mbdx file (only iOS 4)
	if (iOSVersion == 4):
		mbdxPath = backup_path + "Manifest.mbdx"
		if (os.path.exists(mbdxPath)):
			mbdx = mbdbdecoding.process_mbdx_file(mbdxPath)
		else:
			usage()
			print("\nManifest.mbdx not found in path \"%s\". Are you sure this is a correct iOS backup dir, and are you sure this is an iOS 4 backup?\n"%(backup_path))
			sys.exit(1)
	
	# prepares DB
	# database = sqlite3.connect('MyDatabase.db') # Create a database file
	database = sqlite3.connect(':memory:') # Create a database file in memory
	cursor = database.cursor() # Create a cursor
	cursor.execute(
		"CREATE TABLE indice (" + 
		"id INTEGER PRIMARY KEY AUTOINCREMENT," +
		"type VARCHAR(1)," +
		"permissions VARCHAR(9)," +
		"userid VARCHAR(8)," +
		"groupid VARCHAR(8)," +
		"filelen INT," +
		"mtime INT," +
		"atime INT," +
		"ctime INT," +
		"fileid VARCHAR(50)," +
		"domain_type VARCHAR(100)," +
		"domain VARCHAR(100)," +
		"file_path VARCHAR(100)," +
		"file_name VARCHAR(100)," + 
		"link_target VARCHAR(100)," + 
		"datahash VARCHAR(100)," + 
		"flag VARCHAR(100)"
		");"
	)
	
	cursor.execute(
		"CREATE TABLE properties (" + 
		"id INTEGER PRIMARY KEY AUTOINCREMENT," +
		"file_id INTEGER," +
		"property_name VARCHAR(100)," +
		"property_val VARCHAR(100)" +
		");"
	)
		
	# count items parsed from Manifest file
	items = 0;
	
	# populates database by parsing manifest file
	for offset, fileinfo in mbdb.items():
		
		# iOS 4 (get file ID from mbdx file)
		if (iOSVersion == 4):
		
			if offset in mbdx:
				fileinfo['fileID'] = mbdx[offset]
			else:
				fileinfo['fileID'] = "<nofileID>"
				print >> sys.stderr, "No fileID found for %s" % fileinfo_str(fileinfo)
		
		# iOS 5 (no MBDX file, use SHA1 of complete file name)
		elif (iOSVersion == 5):
			fileID = hashlib.sha1()
			fileID.update("%s-%s"%(fileinfo['domain'], fileinfo['filename']) )
			fileinfo['fileID'] = fileID.hexdigest()	
	
		# decoding element type (symlink, file, directory)
		if (fileinfo['mode'] & 0xE000) == 0xA000: type = 'l' # symlink
		elif (fileinfo['mode'] & 0xE000) == 0x8000: type = '-' # file
		elif (fileinfo['mode'] & 0xE000) == 0x4000: type = 'd' # dir
		
		# separates domain type (AppDomain, HomeDomain, ...) from domain name
		[domaintype, sep, domain] = fileinfo['domain'].partition('-');
		
		# separates file name from file path
		[filepath, sep, filename] = fileinfo['filename'].rpartition('/')
		if (type == 'd'):
			filepath = fileinfo['filename']
			filename = "";

		# Insert record in database
		query = "INSERT INTO indice(type, permissions, userid, groupid, filelen, mtime, atime, ctime, fileid, domain_type, domain, file_path, file_name, link_target, datahash, flag) VALUES(";
		query += "'%s'," 	% type
		query += "'%s'," 	% mbdbdecoding.modestr(fileinfo['mode']&0x0FFF)
		query += "'%08x'," 	% fileinfo['userid']
		query += "'%08x'," 	% fileinfo['groupid']
		query += "%i," 		% fileinfo['filelen']
		query += "%i," 		% fileinfo['mtime']
		query += "%i," 		% fileinfo['atime']
		query += "%i," 		% fileinfo['ctime']
		query += "'%s'," 	% fileinfo['fileID']
		query += "'%s'," 	% domaintype.replace("'", "''")
		query += "'%s'," 	% domain.replace("'", "''")
		query += "'%s'," 	% filepath.replace("'", "''")
		query += "'%s'," 	% filename.replace("'", "''")
		query += "'%s'," 	% fileinfo['linktarget']
		query += "'%s'," 	% hex2nums(fileinfo['datahash']).replace("'", "''")
		query += "'%s'" 	% fileinfo['flag']
		query += ");"
		
		#print(query)

		cursor.execute(query)
		
		items += 1;
		
		# check if file has properties to store in the properties table
		if (fileinfo['numprops'] > 0):
	
			query = "SELECT id FROM indice WHERE "
			query += "domain = '%s' " % domain.replace("'", "''")
			query += "AND fileid = '%s' " % fileinfo['fileID']
			query += "LIMIT 1"
			 
			cursor.execute(query);
			id = cursor.fetchall()
			
			if (len(id) > 0):
				index = id[0][0]
				properties = fileinfo['properties']
				for property in properties.keys():
					query = "INSERT INTO properties(file_id, property_name, property_val) VALUES (";
					query += "'%i'," % index
					query += "'%s'," % property
					query += "'%s'" % hex2nums(properties[property]).replace("'", "''")
					query += ");"
					
					cursor.execute(query);
		
			#print("File: %s, properties: %i"%(domain + ":" + filepath + "/" + filename, fileinfo['numprops']))
			#print(fileinfo['properties'])

	database.commit() 
	
	# print banner
	
	banner()
	print("\nWorking directory: %s"%backup_path)
	print("Read elements: %i" %items)
	
	# Builds user interface ----------------------------------------------------------------------------------
	
	# root window
	root = Tkinter.Tk()
	root.geometry("%dx%d%+d%+d" % (1200, 700, 0, 0))
	root.grid_columnconfigure(2, weight=1)
	root.grid_rowconfigure(1, weight=1)

	# left column
	leftcol = Frame(root, relief=RAISED);
	leftcol.grid(column = 0, row = 1, sticky="nsew")
	leftcol.grid_columnconfigure(0, weight=1)
	leftcol.grid_rowconfigure(3, weight=1)
	
	# scrollbars for main tree view
	vsb = ttk.Scrollbar(leftcol, orient="vertical")
	hsb = ttk.Scrollbar(leftcol, orient="horizontal")
	  
	# main tree view definition
	w = Label(leftcol, text="Backup content:", font=globalfont)
	w.grid(column=0, row=2, sticky='ew')
	tree = ttk.Treeview(leftcol, columns=("type", "size", "id"),
	    displaycolumns=("size"), yscrollcommand=lambda f, l: autoscroll(vsb, f, l),
	    xscrollcommand=lambda f, l:autoscroll(hsb, f, l))
	tree.heading("#0", text="Element description", anchor='w')
	tree.heading("size", text="File Size", anchor='w')
	
	if (smallmonitor == 1):
		tree.column("#0", width=200)
		tree.column("size", width=30)
	else:
		tree.column("#0", width=250)
		tree.column("size", width=50)	
	
	vsb['command'] = tree.yview
	hsb['command'] = tree.xview
	tree.grid(column=0, row=3, sticky='nswe')
	vsb.grid(column=1, row=3, sticky='ns')
	hsb.grid(column=0, row=4, sticky='ew')
	
	# device info box
	w = Label(leftcol, text="Device data:", font=globalfont)
	w.grid(column=0, row=0, sticky='ew')
	infobox = Text(leftcol, relief="sunken", borderwidth=2, height=10, width=20, font=globalfont)
	infobox.grid(column=0, row=1, sticky='ew')
	
	# right column
	buttonbox = Frame(root, bd=2, relief=RAISED);
	buttonbox.grid(column = 4, row = 1, sticky="ns", padx=5, pady=5)
	
	w = Label(buttonbox, text="Text search", font=globalfont)
	w.pack()
	
	searchbox = Text(buttonbox, width=20, height=1, relief="sunken", borderwidth=2, font=globalfont)
	searchbox.pack()
	
	w = Button(buttonbox, text="Search", width=10, default=ACTIVE, font=globalfont)
	w.bind("<Button-1>", buttonBoxPress)
	w.pack()

	w = Label(buttonbox, text="Timestamp translation", font=globalfont)
	w.pack()
	
	timebox = Text(buttonbox, width=20, height=1, relief="sunken", borderwidth=2, font=globalfont)
	timebox.pack()
	
	w = Button(buttonbox, text="Convert", width=10, default=ACTIVE, font=globalfont)
	w.bind("<Button-1>", convertTimeStamp)
	w.pack()
	
	w = Button(buttonbox, text="Open reader", width=10, default=ACTIVE, font=globalfont)
	w.bind("<Button-1>", openFile)
	w.pack()

	# tables tree (in right column)
	w = Label(buttonbox, text="Database tables", font=globalfont)
	w.pack()
	
	tablestree = ttk.Treeview(buttonbox, columns=("filename", "tablename"), displaycolumns=())			
	tablestree.heading("#0", text="Tables")
	
	if (smallmonitor == 1):
		tablestree.column("#0", width=150)
	else:
		tablestree.column("#0", width=200)
	tablestree.pack(fill=BOTH, expand=1)
	
	# log row
	logbox = Text(root, relief="sunken", borderwidth=2, height=3, bg='lightgray', font=globalfont)
	logbox.grid(row=4, columnspan=6, sticky='ew')
	
	# header row
	headerbox = Frame(root, bd=2, relief=RAISED);
	icon_path = os.path.dirname(sys.argv[0]) + "/iphone_icon.png"
								
	im = Image.open(icon_path)
	photo = ImageTk.PhotoImage(im)	
	w = Label(headerbox, image=photo)
	w.photo = photo
	w.pack(side=LEFT)	
	
	im = Image.open(icon_path)
	photo = ImageTk.PhotoImage(im)	
	w = Label(headerbox, image=photo)
	w.photo = photo
	w.pack(side=RIGHT)
	
	w = Label(headerbox, text="iPBA - iPhone Backup Analyzer\nVersion: %s (%s)"%(version, creation_date), font=globalfont)
	w.pack()
	
	headerbox.grid(column=0, row=0, sticky='ew', columnspan=6, padx=5, pady=5)

	# center column
	centercolumn = Frame(root, bd=2, relief=RAISED);
	centercolumn.grid(column = 2, row = 1, sticky="nsew")
	centercolumn.grid_columnconfigure(0, weight=1)
	centercolumn.grid_rowconfigure(0, weight=1)

	# main textarea
	textarea = Text(centercolumn, yscrollcommand=lambda f, l: autoscroll(tvsb, f, l),
	    bd=2, relief=SUNKEN, font=globalfont)
	textarea.grid(column=0, row=0, sticky="nsew")

	# scrollbars for main textarea
	tvsb = ttk.Scrollbar(centercolumn, orient="vertical")
	tvsb.grid(column=1, row=0, sticky='ns')
	tvsb['command'] = textarea.yview
	
	# block for selecting limit for browsing table fields
	tableblock = Frame(centercolumn, bd=2, relief=RAISED);
	tableblock.grid(column = 0, row = 1, sticky="nsew")	
	tableblock.grid_columnconfigure(1, weight=1)

	def recordlabelupdate():
		global rowsoffset, rowsnumber
		fieldlabeltext.set("Showing records from %i to %i."%(rowsoffset*rowsnumber, (rowsoffset+1)*rowsnumber-1));
	
	def recordplusbutton(event):
		global rowsoffset
		rowsoffset = rowsoffset+1
		recordlabelupdate()
		TablesTreeClick(None)

	def recordlessbutton(event):
		global rowsoffset
		rowsoffset = rowsoffset-1
		if (rowsoffset < 0): rowsoffset = 0
		recordlabelupdate()
		TablesTreeClick(None)

	fieldless = Button(tableblock, text="<", width=10, default=ACTIVE, font=globalfont)
	fieldless.bind("<Button-1>", recordlessbutton)
	fieldless.grid(column=0, row=0, sticky="nsew")

	fieldlabeltext = StringVar()
	fieldlabel = Label(tableblock, textvariable = fieldlabeltext, relief = RIDGE, font=globalfont)
	fieldlabel.grid(column=1, row=0, sticky="nsew")
	recordlabelupdate()

	fieldplus = Button(tableblock, text=">", width=10, default=ACTIVE, font=globalfont)
	fieldplus.bind("<Button-1>", recordplusbutton)
	fieldplus.grid(column=2, row=0, sticky="nsew")

	# menu --------------------------------------------------------------------------------------------------
	
	def aboutBox():
		aboutTitle = "iPBA iPhone Backup Analyzer"
		aboutText = "(c) Mario Piccinelli 2011 <mario.piccinelli@gmail.com>"
		aboutText += "\n Released under MIT Licence"
		aboutText += "\n Version: " + version
		tkMessageBox.showinfo(aboutTitle, aboutText)
	
	def quitMenu():
		exit(0)
			
	def placesMenu(filename):
		if (filename == ""): return

		query = "SELECT id FROM indice WHERE file_name = \"%s\""%filename
		cursor.execute(query)
		result = cursor.fetchall()
		
		if (len(result) == 0):
			log("File %s not found."%filename)
			return
		
		id = result[0][0]
		nodeFound = searchIndexInTree(id)
		
		if (nodeFound == None):
			log("Node not found in tree while searching for file %s (id %s)."%(filename, id))
			return
			
		tree.see(nodeFound)
		tree.selection_set(nodeFound)
		OnClick("") #triggers refresh of main text area
	
	def base64dec():
		try:
			enctext = textarea.get(SEL_FIRST, SEL_LAST)
			dectext = base64.b64decode(enctext)		
			decstring = ''.join(ch for ch in dectext if ch in string.printable)
			tkMessageBox.showinfo("Decoded Base64 data", decstring)
		except:
			tkMessageBox.showwarning("Error", "Unable to decode selected data.\nMaybe you didn't select the whole data, or the selected data is not encoded in Base64?")

	# Menu Bar
	menubar = Menu(root)
	
	# Places menu
	placesmenu = Menu(menubar, tearoff=0)

	placesmenu.add_command(
		label="Address Book", 
		command=lambda:placesMenu(filename="AddressBook.sqlitedb")
	)
	placesmenu.add_command(
		label="Address Book Images", 
		command=lambda:placesMenu(filename="AddressBookImages.sqlitedb")
	)
	placesmenu.add_command(
		label="Calendar", 
		command=lambda:placesMenu(filename="Calendar.sqlitedb")
	)
	placesmenu.add_command(
		label="Notes", 
		command=lambda:placesMenu(filename="notes.sqlite")
	)
	placesmenu.add_command(
		label="SMS", 
		command=lambda:placesMenu(filename="sms.db")
	)
	placesmenu.add_command(
		label="Safari Bookmarks", 
		command=lambda:placesMenu(filename="Bookmarks.db")
	)
	placesmenu.add_command(
		label="Safari History", 
		command=lambda:placesMenu(filename="History.plist")
	)

	placesmenu.add_separator()
	placesmenu.add_command(label="Write txt", command=writeTXT)
	placesmenu.add_command(label="Decode Base64", command=base64dec)
		
	menubar.add_cascade(label="Places", menu=placesmenu)
	
	# Windows menu
	winmenu = Menu(menubar, tearoff=0)
	
	print("\nLoading plugins...")
	
	print("Loading SMS Browser plugin")
	try:
		import smswindow
		winmenu.add_command(
			label="SMS browser", 
			command=lambda:smswindow.sms_window(
				backup_path + realFileName(filename="sms.db", domaintype="HomeDomain")
			)
		)
	except:
		print(" - Unable to load SMS browser plugin")

	print("Loading Contact Browser plugin")
	try:
		import contactwindow
		winmenu.add_command(
			label="Contacts browser", 
			command=lambda:contactwindow.contact_window(
				backup_path + realFileName(filename="AddressBook.sqlitedb", domaintype="HomeDomain"), 
				backup_path + realFileName(filename="AddressBookImages.sqlitedb", domaintype="HomeDomain")
			)
		)
	except:
		print(" - Unable to load Contact Browser plugin")
	
	print("Loading Safari Bookmarks plugin")
	try:
		import safbookmark
		winmenu.add_command(
			label="Safari Bookmarks", 
			command=lambda:safbookmark.safbookmark_window(
				backup_path + realFileName(filename="Bookmarks.db", domaintype="HomeDomain")
			)
		)
	except:
		print(" - Unable to load Safari Bookmarks plugin")
			
	print("Loading Cell Locations plugin")
	try:
		import celllocation
		winmenu.add_command(
			label="Cell Locations", 
			command=lambda:celllocation.cell_window(
				backup_path + realFileName(filename="consolidated.db", domaintype="RootDomain")
			)
		)
	except:
		print(" - Unable to load Call History plugin")
	
	print("Loading Call History plugin")
	try:
		import callhistory
		winmenu.add_command(
			label="Call history", 
			command=lambda:callhistory.calls_window(
				backup_path + realFileName(filename="call_history.db", domaintype="WirelessDomain")
			)
		)	
	except:
		print(" - Unable to load Call History plugin")	
	
	print("Loading Safari History plugin")
	import safhistory
	winmenu.add_command(
		label="Safari history", 
		command=lambda:safhistory.history_window(
			backup_path + realFileName(filename="History.plist", domaintype="HomeDomain")
		)
	)			
	
	print("Loading complete")
	
	menubar.add_cascade(label="Windows", menu=winmenu)
	
	# ABOUT menu
	helpmenu = Menu(menubar, tearoff=0)
	helpmenu.add_command(label="About", command=aboutBox)
	helpmenu.add_separator()
	helpmenu.add_command(label="Quit", command=quitMenu)
	menubar.add_cascade(label="Help", menu=helpmenu)
	
	# display the menu
	root.config(menu=menubar)
	
	# populate the main tree frame ----------------------------------------------------------------------------
	
	# standard files
	
	tree.tag_configure('base', font=globalfont)
		
	base_files_index = tree.insert('', 'end', text="Standard files", tag='base')
	tree.insert(base_files_index, 'end', text="Manifest.plist", values=("X", "", 0), tag='base')
	tree.insert(base_files_index, 'end', text="Info.plist", values=("X", "", 0), tag='base')
	tree.insert(base_files_index, 'end', text="Status.plist", values=("X", "", 0), tag='base')
	
	cursor.execute("SELECT DISTINCT(domain_type) FROM indice");
	domain_types = cursor.fetchall()
	
	print("\nBuilding UI..")
	
	for domain_type_u in domain_types:
		domain_type = str(domain_type_u[0])
		domain_type_index = tree.insert('', 'end', text=domain_type, tag='base')
		print("Listing elements for domain family: %s" %domain_type)
		
		query = "SELECT DISTINCT(domain) FROM indice WHERE domain_type = \"%s\" ORDER BY domain" % domain_type
		cursor.execute(query);
		domain_names = cursor.fetchall()
		
		for domain_name_u in domain_names:
			domain_name = str(domain_name_u[0])
			
			domain_name_index = tree.insert(domain_type_index, 'end', text=substWith(domain_name, "<no domain>"), tag='base')
			
			query = "SELECT DISTINCT(file_path) FROM indice WHERE domain_type = \"%s\" AND domain = \"%s\" ORDER BY file_path" %(domain_type, domain_name)
			cursor.execute(query)
			paths = cursor.fetchall()
			
			for path_u in paths:
				path = str(path_u[0])
				path_index = tree.insert(domain_name_index, 'end', text=substWith(path, "/"), tag='base')
				
				query = "SELECT file_name, filelen, id, type FROM indice WHERE domain_type = \"%s\" AND domain = \"%s\" AND file_path = \"%s\" ORDER BY file_name" %(domain_type, domain_name, path)
				cursor.execute(query)
				files = cursor.fetchall()
				
				for file in files:
					file_name = str(file[0])
					if (file[1]) < 1024:
						file_dim = str(file[1]) + " b"
					else:
						file_dim = str(file[1] / 1024) + " kb"
					file_id = int(file[2])
					file_type = str(file[3])
					tree.insert(path_index, 'end', text=substWith(file_name, "."), values=(file_type, file_dim, file_id), tag='base')
			
	print("Construction complete.\n")

	# called when an element is clicked in the tables tree frame ------------------------------------------------
	
	def TablesTreeClick(event):
	
		global rowsoffset, rowsnumber
		
		if (event != None): 
			rowsoffset = 0
			recordlabelupdate()

		if (len(tablestree.selection()) == 0): return;
		
		seltable = tablestree.selection()[0]
		seltable_dbname = tablestree.set(seltable, "filename")
		seltable_tablename = tablestree.set(seltable, "tablename")
		
		# clears main text field
		clearmaintext()
				
		# table informations
		maintext("Dumping table: %s\nFrom file: %s"%(seltable_tablename, seltable_dbname))
		log("Dumping table %s from database %s."%(seltable_tablename, seltable_dbname))
		
		if (os.path.exists(seltable_dbname)):
			seltabledb = sqlite3.connect(seltable_dbname)
			try:
				seltablecur = seltabledb.cursor() 
				
				# read selected table indexes
				seltablecur.execute("PRAGMA table_info(%s)" % seltable_tablename)
				seltable_fields = seltablecur.fetchall();
				
				# append table fields to main textares
				seltable_fieldslist = []
				maintext("\n\nTable Fields:")
				for i in range(len(seltable_fields)):
					seltable_field = seltable_fields[i]
					maintext("\n- ")
					maintext("%i \"%s\" (%s)" %(seltable_field[0], seltable_field[1], seltable_field[2]))
					seltable_fieldslist.append(str(seltable_field[1]))

				# count fields from selected table
				seltablecur.execute("SELECT COUNT(*) FROM %s" % seltable_tablename)
				seltable_rownumber = seltablecur.fetchall();
				maintext("\n\nThe selected table has %s rows"%seltable_rownumber[0][0])
				limit = rowsnumber
				offset = rowsoffset*rowsnumber
				maintext("\nShowing %i rows from row %i."%(limit, offset))
							
				# read all fields from selected table
				seltablecur.execute("SELECT * FROM %s LIMIT %i OFFSET %i" % (seltable_tablename, limit, offset))
				seltable_cont = seltablecur.fetchall();
				
				try:
				
					# appends records to main text field
					maintext("\n\nTable Records:")
					
					del photoImages[:]
					
					for seltable_record in seltable_cont:

						maintext("\n- " + str(seltable_record))
							
						for i in range(len(seltable_record)):	
						
							#import unicodedata
							try:
								value = str(seltable_record[i])
							except:
								value = seltable_record[i].encode("utf8", "replace") + " (decoded unicode)"

							#maybe an image?
							if (seltable_fieldslist[i] == "data"):
								dataMagic = magic.whatis(value)
								maintext("\n- Binary data: (%s)" %dataMagic)
								if (dataMagic.partition("/")[0] == "image"):			
								
									im = Image.open(StringIO.StringIO(value))
									tkim = ImageTk.PhotoImage(im)
									photoImages.append(tkim)
									maintext("\n ")
									textarea.image_create(END, image=tkim)
								else:
									maintext("\n\n")	
									maintext(dump(value, 16, 1000))
											
							else:
								try:
									maintext("\n- " + seltable_fieldslist[i] + " : " + value)
								except:
									dataMagic = magic.whatis(value)
									maintext("\n- " + seltable_fieldslist[i] + "  (" + dataMagic + ")")
						
						maintext("\n---------------------------------------")
				
				except:
					print("Unexpected error:", sys.exc_info())
					
				seltabledb.close()		
			except:
				print("Unexpected error:", sys.exc_info())
				seltabledb.close()

	# Called when an element is clicked in the main tree frame ---------------------------------------------------
	
	def OnClick(event):
	
		global fileNameForViewer
	
		if (len(tree.selection()) == 0): return;
		
		# remove everything from tables tree
		for item in tablestree.get_children():
			tablestree.delete(item)
		
		item = tree.selection()[0]
		item_text = tree.item(item, "text")
		item_type = tree.set(item, "type")
		item_id = tree.set(item, "id")
		
		#skip "folders"
		if (item_type == ""): return;
		
		#clears textarea
		clearmaintext()
		
		# managing "standard" files
		if (item_type == "X"):	
			item_realpath = backup_path + item_text
			fileNameForViewer = item_realpath
			maintext("Selected: " + item_realpath)
			log("Opening file %s"%item_realpath)
			
			if (os.path.exists(item_realpath)):		
				
				filemagic = magic.file(item_realpath)
				
				#print file content (if text file) otherwise only first 50 chars
				if (filemagic == "ASCII text" or filemagic.partition("/")[0] == "text"):
					fh = open(item_realpath, 'rb')
					maintext("\n\nASCII content:\n\n")
					while 1:
						line = fh.readline()
						if not line: break;
						maintext(line)
					fh.close()	
				else:
					fh = open(item_realpath, 'rb')
					text = fh.read(30)
					maintext("\n\nFirst 30 chars from file (string): ")
					maintext("\n" + hex2string(text))
					fh.close()
			
				#if binary plist:
				if (filemagic.partition("/")[2] == "binary_plist"):	
					manifest_tempfile = os.path.dirname(sys.argv[0]) + "/out.plist" #default name from perl script plutil.pl
					#os.system("plutil -convert xml1 -o temp01 " + item_realpath)
					command = "perl \"" + os.path.dirname(sys.argv[0]) + "/plutil.pl\" \"%s\" "%item_realpath
					log("Executing: %s"%command)
					os.system(command)
					
					maintext("\n\nDecoding binary Plist file:\n\n")
					
					fh = open(manifest_tempfile, 'rb')
					while 1:
						line = fh.readline()
						if not line: break;
						maintext(line)
					fh.close()				
					os.remove(manifest_tempfile)
			
			else:
				log("...troubles while opening file %s (does not exist)"%item_realpath)
			
			return

		maintext("Selected: " + item_text + " (id " + str(item_id) + ")")
		
		query = "SELECT * FROM indice WHERE id = %s" % item_id
		cursor.execute(query)
		data = cursor.fetchone()
		
		if (len(data) == 0): return
		
		item_permissions = str(data[2])
		item_userid = str(data[3])
		item_groupid = str(data[4])
		item_mtime = str(datetime.fromtimestamp(int(data[6])))
		item_atime = str(datetime.fromtimestamp(int(data[7])))
		item_ctime = str(datetime.fromtimestamp(int(data[8])))
		item_filecode = str(data[9])
		item_link_target = str(data[14])
		item_datahash = str(data[15])
		item_flag = str(data[16])
		
		maintext("\n\nElement type: " + item_type)
		maintext("\nPermissions: " + item_permissions)
		maintext("\nData hash: ")
		maintext("\n " + item_datahash)
		maintext("\nUser id: " + item_userid)
		maintext("\nGroup id: " + item_groupid)
		maintext("\nLast modify time: " + item_mtime)
		maintext("\nLast access Time: " + item_atime)
		maintext("\nCreation time: " + item_ctime)
		maintext("\nFile Key (obfuscated file name): " + item_filecode)
		maintext("\nFlag: " + item_flag)

		# file properties (from properties table, which is data from mbdb file)
		query = "SELECT property_name, property_val FROM properties WHERE file_id = %s" % item_id
		cursor.execute(query)
		data = cursor.fetchall()
		if (len(data) > 0):
			maintext("\n\nElement properties (from mdbd file):")
			for element in data:
				maintext("\n%s: %s" %(element[0], element[1]))
		
		# treat sym links
		if (item_type == "l"):
			maintext("\n\nThis item is a symbolic link to another file.")
			maintext("\nLink Target: " + item_link_target)
			fileNameForViewer = ""
			return
			
		# treat directories
		if (item_type == "d"):
			maintext("\n\nThis item represents a directory.")
			fileNameForViewer = ""
			return
		
		# last modification date of the file in the backup directory
		last_mod_time = time.strftime("%m/%d/%Y %I:%M:%S %p",time.localtime(os.path.getmtime(backup_path + item_filecode)))
		maintext("\n\nLast modification time (in backup dir): %s"%last_mod_time)
		
		maintext("\n\nAnalize file: ")
		
		item_realpath = backup_path + item_filecode
		fileNameForViewer = item_realpath
		
		log("Opening file %s (%s)"%(item_realpath, item_text))
		
		# check for existence 
		if (os.path.exists(item_realpath) == 0):
			maintext("unable to analyze file")
			return			
		
		# print file type (from magic numbers)
		filemagic = magic.file(item_realpath)
		maintext("\nFile tipe (from magic numbers): %s" %filemagic)
		
		# print file MD5 hash
		maintext("\nFile MD5 hash: ")
		maintext(md5(item_realpath))
		
		#print first 30 bytes from file
		fh = open(item_realpath, 'rb')
		first30bytes = fh.read(30)
		maintext("\n\nFirst 30 hex bytes from file: ")
		maintext("\n" + hex2nums(first30bytes))#binascii.b2a_uu(text))
		fh.close()
			
		#print file content (if ASCII file) otherwise only first 30 bytes
		if (filemagic == "ASCII text" or filemagic.partition("/")[0] == "text"):
			fh = open(item_realpath, 'rb')
			maintext("\n\nASCII content:\n\n")
			while 1:
				line = fh.readline()
				if not line: break;
				maintext(line)
			fh.close()	
		else:
			maintext("\n\nFirst 30 chars from file (string): ")
			maintext("\n" + hex2string(first30bytes))					
		
		#if image file:
		if (filemagic.partition("/")[0] == "image"):		
			im = Image.open(item_realpath)
				
			tkim = ImageTk.PhotoImage(im)
			photoImages.append(tkim)
			maintext("\n\nImage data: \n ")
			textarea.image_create(END, image=tkim)
			
		#decode EXIF (only JPG)
		if (filemagic == "image/jpeg"):
			maintext("\n\nJPG EXIF tags:")
			exifs = im._getexif()
			for tag, value in exifs.items():
				decoded = TAGS.get(tag, tag)
				maintext("\nTag: %s, value: %s"%(decoded, value))
				
		#if binary plist:
		if (filemagic.partition("/")[2] == "binary_plist"):	
			manifest_tempfile = os.path.dirname(sys.argv[0]) + "/out.plist" #default name from perl script plutil.pl
			#os.system("plutil -convert xml1 -o temp01 " + item_realpath)
			command = "perl \"" + os.path.dirname(sys.argv[0]) + "/plutil.pl\" \"%s\" "%item_realpath
			log("Executing: %s"%command)
			os.system(command)
			
			maintext("\n\nDecoding binary Plist file:\n\n")
			
			fh = open(manifest_tempfile, 'rb')
			while 1:
				line = fh.readline()
				if not line: break;
				maintext(line)
			fh.close()
			os.remove(manifest_tempfile)	
		
		#if sqlite, print tables list
		if (filemagic.partition("/")[2] == "sqlite"):	
			tempdb = sqlite3.connect(item_realpath) 
			
			try:
				tempcur = tempdb.cursor() 
				tempcur.execute("SELECT name FROM sqlite_master WHERE type=\"table\"")
				tables_list = tempcur.fetchall();
				
				maintext("\n\nTables in database: ")
				
				for i in tables_list:
					table_name = str(i[0])
					maintext("\n- " + table_name);
					
					try:
						tempcur.execute("SELECT count(*) FROM %s" % table_name);
						elem_count = tempcur.fetchone()
						maintext(" (%i elements) " % int(elem_count[0]))
						# inserts table into tables tree
						tablestree.tag_configure('base', font=globalfont)
						tablestree.insert('', 'end', text=table_name, values=(item_realpath, table_name), tag="base")	
					except:
						#probably a virtual table?
						maintext(" (unable to read) ")
						
				tempdb.close()		
				
			except:
				maintext("\n\nSorry, I'm unable to open this database file. It appears to be an issue of some databases in iOS5.")
				maintext("\nUnexpected error: %s"%sys.exc_info()[1])
				tempdb.close()
			
		# if unknown "data", dump hex
		if (filemagic == "data"):
			limit = 10000
			maintext("\n\nDumping hex data (limit %i bytes):\n"%limit)
			content = ""
			fh = open(item_realpath, 'rb')
			while 1:
				line = fh.readline()
				if not line: break;
				content = content + line;
			fh.close()
			
			maintext(dump(content, 16, limit))

	# Main ---------------------------------------------------------------------------------------------------

	tree.bind("<ButtonRelease-1>", OnClick)
	tablestree.bind("<ButtonRelease-1>", TablesTreeClick)
	timebox.bind("<Key>", clearTimeBox)
	
	log("Welcome to the iPhone Backup browser by mario.piccinelli@gmail.com")
	log("Version: %s (%s)"%(version, creation_date))
	log("Working directory: %s"%backup_path)

	maintext("Welcome to the iPhone Backup browser by mario.piccinelli@gmail.com")
	maintext("\nVersion: %s (%s)"%(version, creation_date))
	maintext("\nWorking directory: %s"%backup_path)
	
	deviceinfo = decodeManifestPlist.deviceInfo(backup_path + "Info.plist")
	for element in deviceinfo.keys():
		infobox.insert(INSERT, "%s: %s\n"%(element, deviceinfo[element]))

	root.focus_set()
	
	root.mainloop()
	
	database.close() # Close the connection to the database
	
