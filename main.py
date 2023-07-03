import os
import selenium as sl
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.alert import Alert
import pprint
import json

import time
import threading
import logging

import tkinter as tk

pp = pprint.PrettyPrinter(depth=4)

playerListFile = '../players'
roomListFile = '../roomNames'
stateFile = '../state'
loginFile = '../loginDetails'
prefix = 'FC '

pauseMain = True
killMain  = False
statusString = False
addString = False
removeString = False
playersToAdd = []
playersToRemove = []
wantSuddenDeath = False
forceUpdate = 0

CYCLE_PERIOD = 10
WANT_FILL = '_WANT_FILL_'

state = {}

def WriteState(state):
	with open(stateFile + '.json', 'w') as outfile:
		json.dump(state, outfile, indent=4)


def ReadState():
	with open(stateFile + '.json', 'r') as f:
		return json.load(f)


def LoadFileToList(fileName):
	with open('{}.txt'.format(fileName)) as file:
	    lines = [line.rstrip() for line in file]
	return lines


def ListRemove(myList, element):
	if element not in myList:
		return myList
	myList = myList.copy()
	myList.remove(element)
	return myList


def DictRemove(myDict, element):
	if element not in myDict:
		return myDict
	myDict = myDict.copy()
	myDict.pop(element)
	return myDict


def GetListInput(question, choices):
	for i, choice in enumerate(choices):
		question = question + ' [{}] {},'.format(i + 1, choice)
	question = question[:-1] + ': '
	
	validResponses = [str(i + 1) for i in range(len(choices))]
	response = input(question)
	while response not in (validResponses + choices):
		response = input(question)
	if response in choices:
		return response
	return choices[int(response) - 1]


def InitialiseWebDriver():
	loginDetails = LoadFileToList(loginFile)
	# Using Chrome to access web
	driver = sl.webdriver.Chrome()# Open the website
	
	driver.get('https://zero-k.info')
	driver.implicitly_wait(0.5)
	
	nameBox = driver.find_element(By.NAME, 'login')
	nameBox.send_keys(loginDetails[0])
	
	
	nameBox = driver.find_element(By.NAME, 'password')
	nameBox.send_keys(loginDetails[1])
	
	login_button = driver.find_element(By.NAME,'zklogin')
	login_button.click()
	
	driver.get('https://zero-k.info/Tourney')
	driver.implicitly_wait(0.5)
	return driver


def ProcessTableRow(row):
	elementList = row.find_elements(By.XPATH, ".//*")
	elements = {e.text : e for e in elementList}
	elementNames = list(elements.keys())
	rowData = {}
	if 'Force join' in elements:
		rowData['forceJoin'] = elements['Force join']
	if 'Delete' in elements:
		rowData['delete'] = elements['Delete']
	
	rowData['playersJoined'] = (elementNames[0].count('  IN') > 1)
		
	if elementNames[4] == '  IN':
		rowData['players'] = [elementNames[3], elementNames[5]]
	else:
		rowData['players'] = [elementNames[3], elementNames[4]]
	
	selectNext = False
	for name, element in elements.items():
		if selectNext and element.text.count(' ') == 0:
			rowData['battleID'] = element.text[1:]
			break
		if name.count(' 2 on ') > 0:
			selectNext = True
	return elementNames[1], rowData


def GetRoomTable(driver):
	tables = driver.find_elements(By.TAG_NAME, 'table')
	elements = False
	for table in tables:
		if table.text.count('Force join') > 0:
			elements = table.find_elements(By.XPATH, ".//*")
			break
	if elements is False:
		return False

	rows = {}
	for e in elements:
		if e.text.count(prefix) == 1 and e.text.count('Force join') == 1:
			name, rowData = ProcessTableRow(e)
			rows[name] = rowData
	return rows


def InitializeState():
	if os.path.isfile(stateFile + '.json'):
		state = ReadState()
		return state
	players = LoadFileToList(playerListFile)
	roomNames = LoadFileToList(roomListFile)
	random.shuffle(players)
	
	state = {
		'queue' : players,
		'maxQueueLength' : 2,
		'playerRoomPreference' : {},
		'toDelete' : [],
		'rooms' : {name : {
			'name' : name,
			'index' : 0,
			'finished' : True,
		} for name in roomNames},
		'completedGames' : {},
	}
	WriteState(state)
	return state


def PrintState(state):
	global statusString
	runningRooms = [data for name, data in state['rooms'].items() if not data['finished']]
	status = 'Queue: {}'.format(state['queue'])
	print(status)
	for room in runningRooms:
		roomSummary = '{}: {} vs {}'.format(
			room['createdName'], room['players'][0], room['players'][1])
		status = status + '\n' + roomSummary
		print('Running: ' + roomSummary)
	statusString.set(status)


def FindRoomForPlayers(state, players):
	checkRooms = []
	for name in players:
		if name in state['playerRoomPreference']:
			checkRooms.append(state['playerRoomPreference'][name])
	checkRooms = checkRooms + list(state['rooms'].keys())
	
	for room in checkRooms:
		if state['rooms'][room]['finished']:
			state['rooms'][room]['finished'] = False
			return state['rooms'][room]
	return False


def ReplaceWantFill(state, player):
	fillIndex = [i for i, x in enumerate(state['queue']) if x == WANT_FILL][0]
	state['queue'][fillIndex] = player
	return state


def MakeRooms(driver, roomsToMake):
	roomStr = ''
	first = True
	for name, data in roomsToMake.items():
		if first:
			first = False
		else:
			roomStr = roomStr + '//'
		roomStr = roomStr + '{},{},{}'.format(name, data[0], data[1])
	massRoomField = driver.find_element(By.NAME,'battleList')
	massRoomField.clear()
	massRoomField.send_keys(roomStr)
	
	createBattles = driver.find_element(
		By.XPATH,
		'//input[@type="submit" and @value="Create Battles" and contains(@class, "js_confirm")]')
	createBattles.click()
	
	alert = Alert(driver)
	alert.accept()
	
	joinAttempts = {}
	tryForceJoin = True
	while tryForceJoin:
		driver.implicitly_wait(0.5)
		tryForceJoin = False
		rows = GetRoomTable(driver)
		for name, rowData in rows.items():
			if name in roomsToMake:
				if name not in joinAttempts:
					joinAttempts[name] = 0
				if 'forceJoin' in rowData and not rowData['playersJoined'] and joinAttempts[name] < 4:
					print('Force joining ' + name)
					rowData['forceJoin'].click()
					joinAttempts[name] = joinAttempts[name] + 1
					driver.implicitly_wait(0.5 * joinAttempts[name])
					tryForceJoin = True
					break
	return {n : (v < 4) for n, v in joinAttempts.items()}


def SetupRequiredRooms(driver, state):
	rooms = {}
	while (len(state['queue']) > state['maxQueueLength']) and (WANT_FILL not in state['queue'][:2]):
		room = FindRoomForPlayers(state, state['queue'][:2])
		room['index'] = room['index'] + 1
		room['players'] = state['queue'][:2]
		room['createdName'] = '{}{} {}'.format(prefix, room['name'], room['index'])
		rooms[room['createdName']] = state['queue'][:2]
		state['queue'] = state['queue'][2:]
		print('Adding room "{}": {} vs {}'.format(
			room['createdName'], room['players'][0], room['players'][1]))
	
	if len(rooms) > 0:
		success = MakeRooms(driver, rooms)
	return state


def CleanUpRooms(driver, state):
	if len(state['toDelete']) == 0:
		return state
	
	for roomName in state['toDelete']:
		pageRooms = GetRoomTable(driver)
		print('Trying to delete', roomName)
		if (pageRooms is not False) and (roomName in pageRooms) and ('delete' in pageRooms[roomName]):
			print('Deleting', roomName)
			pageRooms[roomName]['delete'].click()
			alert = Alert(driver)
			alert.accept()
			driver.implicitly_wait(0.5)
			state['toDelete'].remove(roomName)
	return state


def HandleRoomFinish(state, room, battleID, winner=False):
	if room not in state['rooms']:
		return state
	roomData = state['rooms'][room]
	if roomData['finished']:
		return state
	
	if winner is False:
		winner = GetListInput('Who won?', roomData['players'])
	loser     = ListRemove(roomData['players'], winner)[0]
	forumLink = '@B{}'.format(battleID)
	
	roomData['finished'] = True
	state['toDelete'].append(roomData['createdName'])
	if len(state['queue']) == 0:
		state['queue'] = [winner, WANT_FILL, loser]
	elif WANT_FILL in state['queue']:
		state = ReplaceWantFill(state, winner)
		state['queue'] = state['queue'] + [loser]
	else:
		state['queue'] = [winner] + state['queue'] + [loser]
	state['playerRoomPreference'][winner] = room
	state['playerRoomPreference'] = DictRemove(state['playerRoomPreference'], loser)
	state['completedGames'][forumLink] = {
		'series' : room,
		'name'   : roomData['createdName'],
		'winner' : winner,
		'lower'  : loser,
	}
	return state


def GetBattleWinner(driver, battleID):
	print('Checking battle "{}"'.format(battleID))
	driver.get('https://zero-k.info/Battles/Detail/{}?ShowWinners=True'.format(battleID))
	driver.implicitly_wait(0.5)
	
	winnerBox = driver.find_element(By.CLASS_NAME, 'fleft.battle_winner')
	elements = winnerBox.find_elements(By.XPATH, ".//*")
	userNameBox = winnerBox.find_element(By.CSS_SELECTOR, "a[href^='/Users/Detail/']")
	return userNameBox.text


def UpdateGameState(driver, state):
	driver.get('https://zero-k.info/Tourney') # Refresh page
	driver.implicitly_wait(0.5)

	pageRooms = GetRoomTable(driver)
	needReturnToPage = False
	if pageRooms is False:
		return state
	
	for baseName, roomData in state['rooms'].items():
		if 'createdName' in roomData and roomData['createdName'] in pageRooms:
			pageData = pageRooms[roomData['createdName']]
			if 'battleID' in pageData and (not roomData['finished']):
				winner = GetBattleWinner(driver, pageData['battleID'])
				state = HandleRoomFinish(state, baseName, pageData['battleID'], winner=winner)
				needReturnToPage = True
	
	if needReturnToPage:
		driver.get('https://zero-k.info/Tourney')
		driver.implicitly_wait(0.5)
	return state


def RemovePlayerFromState(state, player):
	if player in state['queue']:
		state['queue'].remove(player)
		return state
	for name, roomData in state['rooms'].items():
		if player in roomData['players']:
			roomData['finished'] = True
			state['toDelete'].append(roomData['createdName'])
			otherPlayer = ListRemove(roomData['players'], player)[0]
			state['queue'] = [otherPlayer] + state['queue']
			return state


def CheckAddOrRemovePlayers(state):
	global playersToAdd, playersToRemove, addString, removeString
	if len(playersToAdd) > 0:
		if WANT_FILL in state['queue']:
			state = ReplaceWantFill(state, playersToAdd[0])
			state['queue'] = state['queue'] + playersToAdd[1:]
		else:
			state['queue'] = state['queue'] + playersToAdd
		playersToAdd = []
		if addString is not False:
			addString.set('')
	if len(playersToRemove) > 0:
		for player in playersToRemove:
			RemovePlayerFromState(state, player)
		playersToRemove = []
		if removeString is not False:
			removeString.set('')
	return state


def WriteAndPause(state):
	global forceUpdate
	PrintState(state)
	WriteState(state)
	updateTimer = 0
	while pauseMain or (updateTimer < CYCLE_PERIOD and forceUpdate == 0):
		time.sleep(0.5)
		updateTimer = updateTimer + 0.5
	forceUpdate = max(0, forceUpdate - 1)
	state = ReadState()
	state = CheckAddOrRemovePlayers(state)
	return state


def AutonomousUpdateThread():
	global state
	state = InitializeState()
	driver = InitialiseWebDriver()
	print('Main thread started')
	while (not killMain):
		state = WriteAndPause(state)
		if killMain:
			return
		state = SetupRequiredRooms(driver, state)
		print('=========== Rooms Created ===========')
		state = CleanUpRooms(driver, state)
		print('=========== Rooms Deleted ===========')
		PrintState(state)
	
		state = WriteAndPause(state)
		if killMain:
			return
		state = UpdateGameState(driver, state)
		print('=========== State Updated ===========')


def TestThread():
	while (not killMain):
		print('pauseMain', pauseMain)
		time.sleep(1)


lastTextString = False
lastPlayerNames = False
tabIndex = 0

def SetupWindow():
	global statusString, addString, removeString
	global playersToAdd, playersToRemove
	window = tk.Tk()
	
	statusString = tk.StringVar()
	statusString.set("Status")
	
	pauseString = tk.StringVar()
	pauseString.set("PAUSED")
	
	addString = tk.StringVar()
	addString.set("")
	removeString = tk.StringVar()
	removeString.set("")
	
	def Resume():
		global pauseMain, forceUpdate
		pauseMain = False
		forceUpdate = 2
		pauseString.set("ACTIVE")
		
	def Pause():
		global pauseMain
		pauseMain = True
		pauseString.set("PAUSED")
	
	def AddPlayer():
		global forceUpdate
		name = txtfld.get()
		txtfld.delete(0, tk.END)
		if len(name) > 0 and name not in playersToAdd:
			playersToAdd.append(name)
			addString.set('Adding: ' + str(playersToAdd))
			forceUpdate = 2
	
	def RemovePlayer():
		global forceUpdate
		name = txtfld.get()
		txtfld.delete(0, tk.END)
		if len(name) > 0 and name not in playersToRemove:
			playersToRemove.append(name)
			removeString.set('Removing: ' + str(playersToRemove))
			forceUpdate = 2
	
	def PrintBattles():
		global state
		print('Battle Links')
		for name in list(state['completedGames'].keys()):
			print(name)
	
	def TabPressed(event):
		global lastTextString, lastPlayerNames, tabIndex
		name = txtfld.get()
		if len(name) == 0 or state is False:
			return 'break'
		if name != lastTextString:
			playerNames = state['queue'].copy()
			for room, roomData in state['rooms'].items():
				if 'players' in roomData:
					playerNames = playerNames + roomData['players']
			playerNames = list(set(playerNames))
			playerNames = [x for x in playerNames if name in x]
			if len(playerNames) == 0:
				return 'break'
			lastPlayerNames = playerNames
			tabIndex = 0
		else:
			playerNames = lastPlayerNames
			tabIndex = (tabIndex + 1)%len(playerNames)
		
		lastTextString = playerNames[tabIndex]
		txtfld.delete(0, tk.END)
		txtfld.insert(0, lastTextString)
		return 'break'

	window.bind("<Tab>", TabPressed)
	
	offset = 20
	labelSpacing = 40
	spacing = 50
	fontSmall = ("Helvetica", 12)
	font      = ("Helvetica", 16)
	fontBig   = ("Helvetica", 24)
	
	label = tk.Label(window, textvariable=pauseString, font=fontBig, justify=tk.LEFT)
	label.place(x=20, y=offset)
	btn = tk.Button(window, text="Print", fg='blue', command=PrintBattles, font=font, width=8)
	btn.place(x=260, y=offset)
	offset = offset + spacing
	
	btn = tk.Button(window, text="Resume", fg='blue', command=Resume, font=font, width=8)
	btn.place(x=20, y=offset)
	btn = tk.Button(window, text="Pause", fg='blue', command=Pause, font=font, width=8)
	btn.place(x=140, y=offset)
	offset = offset + spacing
	
	btn = tk.Button(window, text="Add", fg='blue', command=AddPlayer, font=font, width=8)
	btn.place(x=20, y=offset)
	btn = tk.Button(window, text="Remove", fg='blue', command=RemovePlayer, font=font, width=8)
	btn.place(x=140, y=offset)
	
	label = tk.Label(window, textvariable=addString, font=fontSmall, justify=tk.LEFT)
	label.place(x=260, y=offset)
	label = tk.Label(window, textvariable=removeString, font=fontSmall, justify=tk.LEFT)
	label.place(x=260, y=offset + 40)
	
	offset = offset + spacing
	
	txtfld = tk.Entry(window, text="Player Names", bd=5, font=font, width=18)
	txtfld.place(x=20, y=offset)
	offset = offset + labelSpacing
	
	label = tk.Label(window, textvariable=statusString, font=font, justify=tk.LEFT)
	label.place(x=20, y=offset)
	offset = offset + spacing
	
	window.title('Tournament Bot')
	window.geometry("500x500+1050+200")
	window.mainloop()
	
	pauseMain = True
	killMain = True
	PrintBattles()


def SetupThreads():
	mainThread = threading.Thread(target=AutonomousUpdateThread)
	mainThread.daemon = True
	mainThread.start()
	
	SetupWindow()


def DoManualMode():
	state = InitializeState()
	driver = InitialiseWebDriver()
	
	while True:
		state = ReadState()
		state = SetupRequiredRooms(driver, state)
		WriteState(state)
		print('=========== Rooms Created ===========')
		PrintState(state)
		input('Press enter')
			
		state = ReadState()
		state = UpdateGameState(driver, state)
		WriteState(state)
		print('=========== State Updated ===========')
		PrintState(state)
		input('Press enter')
	
SetupThreads()
#DoManualMode()

