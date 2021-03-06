import argparse
import subprocess
import os
import time
import requests
from threading import Event, Thread
from threading import Timer

import threading
import _thread
import socket

import predict


DIR_PATH = os.path.dirname(os.path.realpath(__file__))

FACIAL_EXPRESSIONS = ['attention','browFurrow','browRaise','cheekRaise','chinRaise','dimpler','eyeClosure','eyeWiden','innerBrowRaise',
                      'jawDrop','lidTighten','lipCornerDepressor','lipPress','lipPucker','lipSuck','mouthOpen','noseWrinkle','smile','smirk','upperLipRaise']

EMOTIONS = ['joy','sadness','disgust','contempt','anger','fear','surprise','valence','engagement']

WEBSITES = {'socialNetwork':['facebook','instagram','twitter','tumblr'],
           'shopping':['amazon','craigslist','bestbuy'],
           'entertainment':['youtube','reddit','buzzfeed','pinterest'],
           'general':['news','blog','board','game','shopping'],
           'work':['github','overleaf','blackboard','qualtrics','surveymonkey','stack overflow']}

PORT = 8899

    
class Monitor():
    
    def __init__(self, sendMsg = False, saveFile = None):
        
        self.sendMsg = sendMsg
        self.predictor = None
        self.model = None
        self.socketOpen = False
        self.c = None
        self.addr = None
        self.s = None        
        self.predictionData = []
        
        
        if sendMsg:
            _thread.start_new_thread(self.open_socket, ())
        else:
            # Check if the saveFile exsits, if not, create a new file
            if saveFile is None:
                self.saveFile = os.path.join(DIR_PATH, "data", "test.txt")
            else:
                self.saveFile = os.path.join(DIR_PATH, "data", saveFile)

            print("Created a new file at: {0}".format(self.saveFile))
            open(self.saveFile, 'w').close()    
            
            # Write the header    
            header = []
            header.append("label")
            header.append("wordsPerMinute")

            for key in FACIAL_EXPRESSIONS:
                header.append(key)
            for key in WEBSITES:
                header.append("active_{0}".format(key))
            header.append("active_other")
            for key in WEBSITES:
                header.append("open_{0}".format(key))

            with open(self.saveFile, 'w') as f:
                out = [str(x) for x in header]
                f.write(",".join(out))
                f.write('\n')  
        
        self.last_facial_expression_stored = {}
        for key in FACIAL_EXPRESSIONS:
            self.last_facial_expression_stored[key] = 0   

                
                
    def run(self, state = 'working'):
                
        # Assumes that the keylogger, the web server is running
        timer = RepeatedTimer(5, self.logData, state)
        # start timer
        timer.start()
        
        if self.sendMsg:
            pass
        else:
            var = input("Please enter 'w' for working state, and 'd' for distracted state. Enter 'x' to stop recording data")

            if var == 'w':
                timer.stop()
                self.run("working")
            elif var == 'd':
                timer.stop()            
                self.run("distracted")
            else:
                timer.stop()
        
        
    def logData(self, state):
        
        data = []
        ind = 0
        
        if state == "working":
            data.append(1)
        else: # distracted
            data.append(0)
        
        self.request_facial_expression()
        facial_expression = self.read_facial_expression()
        
        self.write_open_windows()
        active_window, open_windows = self.read_open_windows()
        
        words_typed_per_minute = self.read_keylogger_data()
        data.append(words_typed_per_minute)
            
        allZero = True
        for key in facial_expression:
            if facial_expression[key] != 0:
                allZero = False
        if allZero:
            print("Using the last facial expression data...")
            for key in FACIAL_EXPRESSIONS:
                facial_expression[key] = self.last_facial_expression_stored[key]                    
        else:
            for key in FACIAL_EXPRESSIONS:
                self.last_facial_expression_stored[key] = facial_expression[key]        
                
        for key in FACIAL_EXPRESSIONS:
            data.append(facial_expression[key])

                
        if active_window:
            categoryFound = False
            for category in WEBSITES:
                
                titleMatchFound = False
                for key in WEBSITES[category]:
                    if key in active_window.lower():
                        titleMatchFound = True
                        categoryFound = True
                        break
                
                if titleMatchFound: # Set 1 if a page is found to be in the current category
                    data.append(1)
                else:
                    data.append(0)
                    
            if categoryFound: # Category "others"
                data.append(0)
            else:
                data.append(1)
                    
        else:
            for category in WEBSITES:
                data.append(0)
            data.append(0)
            
        if open_windows:
            for category in WEBSITES:
                counter = 0
                for window in open_windows:
                    title = window.lower()
                    for key in WEBSITES[category]:
                        if key in title:
                            counter += 1
                data.append(counter)
        else:
            for key in WEBSITES:
                data.append(0)
                
        
        if self.sendMsg: # Send data to the robot
            if self.model is None:
                raise ValueError("Model is not set up")
            else:
                # Remove the label
                data = data[1:]
                # Make prediction
                
                self.predictionData.append(data)
                
                if len(self.predictionData) == 10:
                    del self.predictionData[0]
                    
                prediction = self.model.predict(self.predictionData)
                prediction = prediction[-1] # Get the last element
                if prediction == 0:
                    print("Prediction: Distracted")
                else:
                    print("Prediction: Working")
                
                # Send message to the robot
                self.send_message(str(prediction))
            
        else: # Log data in a file
            with open(self.saveFile, 'a') as f:
                out = [str(x) for x in data]
                f.write(",".join(out))
                f.write('\n')
                print("Logged data with {0} features".format(len(data)))
                print(",".join(out))
            
        
        
    def setModel(self, modelFilePath):
        self.model = predict.Predictor(modelFilePath)
            
    def read_keylogger_data(self):
        keyloggerData = os.path.join(DIR_PATH, "data.log")
        
        numWords = []
        elapsed_time = []
        
        try:
            with open(keyloggerData, 'r') as f: 
                counter = 0
                for line in f:
                    if "Words: " in line:
                        words = line.split()
                        numWords.append(len(words))
                    elif "Elapsed Time: " in line:
                        split = line.split()
                        time = int(split[2])
                        elapsed_time.append(time)
                    else:
                        pass
                        
            # Get the last line
            try:
                words_per_minute = numWords[-1] / elapsed_time[-1] * 60
            except IndexError as e:
                words_per_minute = 0
                
            return words_per_minute
            
        except IOError as e:
            print(str(e))
            return 0

    
    def request_facial_expression(self):
        requests.post("http://localhost:{0}/get-facial-expression".format(PORT), data = {'key':'value'})
        
    def read_facial_expression(self):
        data_file = os.path.join(DIR_PATH, "web", "facial_expressions.txt")        

        try:
            waitForFileGeneration(data_file)        
            facial_expressions = {}            
            
            with open(data_file, 'r') as f: 
                for i, line in enumerate(f):
                    if line.isspace():
                        pass
                    else:
                        lineSplit = line.split(":")
                        number = float(lineSplit[1].strip())
                        facial_expressions[lineSplit[0]] = number
            return facial_expressions

        except OSError as e:
            print("Encountered trouble in reading facial_expressions.txt")
            print(str(e))
            facial_expressions = {}
            for exp in FACIAL_EXPRESSIONS:
                facial_expressions[exp] = 0            
            return facial_expressions            
                        
    def write_open_windows(self):
        script_path = os.path.join(DIR_PATH, "applescript", "windows_monitor.scpt")
        subprocess.check_call("osascript {0}".format(script_path), shell=True)    

    def read_open_windows(self):
        data_file = os.path.join(DIR_PATH, "applescript", "open_windows.txt")
        
        waitForFileGeneration(data_file)
        
        active_tab_URL = None
        active_tab_title = None
        open_tab_URL = []
        open_tab_title = []
        open_applications = []

        try:
            with open(data_file, 'r') as f: 
                inputType = 0
                for i, line in enumerate(f):
                    if line.isspace():
                        pass
                    elif "-----" in line:
                        inputType += 1
                    else:
                        if inputType == 0: # Active chrome tab URL & title
                            if i == 0:
                                active_tab_URL = line
                            else:
                                active_tab_title = line
                        elif inputType == 1: # All chrome tab URLs
                            open_tab_URL.append(line)
                        elif inputType == 2: # All chrome tab titles
                            open_tab_title.append(line)
                        elif inputType == 3: # All applications open
                            lineSplit = line.split(",")
                            open_applications = lineSplit
            os.remove(data_file)
            
            return active_tab_title, open_tab_title

        except Error as e:
            print("Error in reading the window monitor file")
            print(str(e))
            
            return None, None
            
    def open_socket(self):
        # Provides prediction service for the robot manipulation script
        try:
            print("Opening socket connection")
            s = socket.socket()
            ip = ""
            port = 20000
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((ip, port))
            s.listen(5)
            c, addr = s.accept()
            self.c = c
            self.addr = addr
            self.s = s
            self.socketOpen = True
            return True
            
        except OSError as e:
            print(str(e))
            self.close_socket()
            return False
        
    def send_message(self, state = "0"):
        try:
            if self.socketOpen:
                print("Sending prediction result \"{}\" to 127.0.0.1:20000".format(state))
                self.c.send(state.encode())            
        except OSError:
            self.close_socket()
            
    
    def close_socket(self):
        print("Closing socket connection")
        if self.c:
            self.c.close()
        if self.s:
            self.s.close()               
            
            
def waitForFileGeneration(filePath, trial = 3, interval = 1):
    max_i = trial
    for i in range(max_i):
        try:
            with open(filePath, 'r') as f:
                f.close()
                break
        except IOError:
            time.sleep(interval)
    else:
        raise IOError('Could not access {} after {} attempts'.format(filePath, str(max_i)))


class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer     = None
        self.interval   = interval
        self.function   = function
        self.args       = args
        self.kwargs     = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False
        


if __name__=='__main__':
    
    parser = argparse.ArgumentParser(description='Run scripts to monitor user behavior')
        
    parser.add_argument('--sendMsg', action='store_true',
                        help='Send message to the robot through socket. (Does not create data file)')    
    
    parser.add_argument('--model', type=str, default=None, help='Name of the pickled model file')    
    
    
    args = parser.parse_args()
    option = None
    model = None
    
    if args.sendMsg:
        if args.model is None:
            raise ValueError("Model path not given")
        else:
            model = args.model
            
        option = "sendMsg"  
            
    monitor = Monitor(option)
    
    if model is not None:
        monitor.setModel(model)
    
    monitor.run()  
    
    
    
