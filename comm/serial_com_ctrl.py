from tkinter import messagebox
import serial.tools.list_ports
import time
import tkinter as tk

class SerialCtrl():
    def __init__(self):
        self.sync_cnt = 10
    
    def getCOMList(self):
        ports = serial.tools.list_ports.comports()
        self.com_list = [com[0] for com in ports]
        self.com_list.insert(0, "-")
        
    def SerialOpen(self, gui):
        try:
            self.ser.is_open 
        except:
            PORT = gui.selected_com.get()
            BAUD = gui.selected_bd.get()
            self.ser = serial.Serial()
            self.ser.baudrate = BAUD
            self.ser.port = PORT
            self.ser.timeout = 0.1
        
        try:
            if self.ser.is_open:
                self.ser.status = True
            else:
                PORT = gui.selected_com.get()
                BAUD = gui.selected_bd.get()
                self.ser = serial.Serial()
                self.ser.baudrate = BAUD
                self.ser.port = PORT
                self.ser.timeout = 0.1
                self.ser.open()
                self.ser.status =True
        except:
            self.ser.status = False
                    
    def SerialClose(self):
        try:
            self.ser.is_open
            self.ser.close()
            self.ser.status = False
        except:
            self.ser.status = False
      
    def Close_Com(self):
        if hasattr(self, 'ser'):
            self.ser.close()
            
    def is_port_available(self):
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if port.device == self.ser.port:
                return True
        return False
            
    def Monitor_Connection(self, gui):
        self.monitor_thread_running = True  # Control flag for the thread
        while self.monitor_thread_running:
            if not self.is_port_available():
                self.stop_monitor_thread(gui)
                self.ser = None
            time.sleep(1)  # Poll every second
    
    def stop_monitor_thread(self, gui):
       self.monitor_thread_running = False
       self.threading = False
     
       # Start closing the connection
       self.SerialClose()   
       gui.data.ClearData()
       
       InfoMsg = f"UART connection using {gui.selected_com.get()} is closed"
       messagebox.showinfo("info", InfoMsg)
       
       gui.datacollect.clt_m1.config(state='normal')
       gui.datacollect.clt_m2.config(state='normal')
       gui.datacollect.Load_fre.config(state='normal')
   
       gui.btn_connect["text"] = "Connect"
       gui.sync_status["text"] = "..Sync.."
       gui.sync_status["fg"] = "orange"
       gui.btn_refresh["state"] = "active"
       gui.drop_baud["state"] = "active"
       gui.drop_com["state"] = "active"
       gui.datacollect.load_status["text"] = "Pending..."
       gui.datacollect.load_status["fg"] = "orange"
       gui.datacollect.node_status_txt["text"] = "Active Node Status"
       gui.datacollect.node_status["text"] = "Pending..."
       gui.datacollect.node_status["fg"] = "orange"
       gui.datacollect.complete_nodes["text"] = "Pending..."
       gui.datacollect.complete_nodes["fg"] = "orange"
       gui.datacollect.ACK_status["text"] = "Pending..."
       gui.datacollect.ACK_status["fg"] = "orange"
       gui.datacollect.time_cal_status["text"] = "Pending..."
       gui.datacollect.time_cal_status["fg"] = "orange"
       gui.datacollect.freID_status["text"] = "Pending..."
       gui.datacollect.freID_status["fg"] = "orange"
       gui.datacollect.data_rec_status["text"] = "Pending..."
       gui.datacollect.data_rec_status["fg"] = "orange"
       gui.datacollect.data_save_status["text"] = "Pending..."
       gui.datacollect.data_save_status["fg"] = "orange"
       gui.datacollect.btn_collection["text"] = "Start Collection"
       gui.datacollect.btn_collection["bg"] = "#eff0f7"
       gui.datacollect.btn_collection["fg"] = "black"
            
    def WorkingIDs_UART_TX(self, gui):
        for i in range(0, len(gui.data.working_nodes), 8):
            chunk = gui.data.working_nodes[i:i+8]
            chartouart = f"#C#{len(chunk)}#"

            #working node id: 0-255
            for IDs in chunk:
                # IDs is a digit string like "9" or "11"; zero-pad the WHOLE
                # value to 3 chars, not just its first character (the old
                # IDs[0].zfill(3) sent "001" for every node 10..19).
                chartouart += f"{IDs.zfill(3)}"

            chartouart += "\n"
            self.ser.write(chartouart.encode())
            
                
    def FrequencyID_UART_TX(self, gui): 
        for i in range(0, len(gui.data.fre_IDs), 3):
            chunk = gui.data.fre_IDs[i:i + 3]
            chartouart = f"#C#{len(chunk)}#"
            for IDs in chunk:
                highByte = (IDs[0] >> 8) & 0xFF   # Extract the high byte
                lowByte = IDs[0] & 0xFF           # Extract the low byte
                chartouart += f"{highByte:d}{lowByte:03d}"
             
            chartouart += "\n"
            self.ser.write(chartouart.encode())
            
        
    def SerialSync(self, gui):
        self.threading = True
        cnt = 0
        while self.threading:
            try:
                self.ser.write(gui.data.sync_out.encode())
                gui.sync_status["text"] = "..Sync.."
                gui.sync_status["fg"] = "orange"
                gui.data.RowMsg = self.ser.readline()
                
                if gui.data.RowMsg: 
                    #print(f"RowMsg: {gui.data.RowMsg}") 
                    gui.data.DecodeMsg()
                    if gui.data.sync_ok:
                        gui.sync_status["text"] = "OK"
                        gui.sync_status["fg"] = "green"
                        
                        self.threading = False
                        break
                    
                if self.threading == False: break
            except Exception as e:
                print(e)
            cnt += 1
            if self.threading == False: break
            if cnt > self.sync_cnt:
                cnt = 0
                gui.sync_status["text"] = "Failed"
                gui.sync_status["fg"] = "red"
                time.sleep(0.5)
                if self.threading == False: break
            
                
    def SerialStream(self, gui):
        self.threading = True
        
        gui.complete_nodes["text"] = "None"
        gui.complete_nodes["fg"] = "black"
      
        # TXWIDs, TXFreIDs, MXStart TimeRqst, RandomRqst, DataRec, WaitforMCU, MXStop
        self.SerState = "TXWIDs"
        
        
        while self.threading:
            
            if not self.threading: break
        
            if self.SerState == "TXWIDs":
                # Send working IDs
                WIDHead = f"#F#{len(gui.data.working_nodes):03d}\n"
                self.ser.write(WIDHead.encode())
                self.WorkingIDs_UART_TX(gui)
                WIDTail = "#P#\n"
                self.ser.write(WIDTail.encode())
            elif self.SerState == "TXFreIDs":
                FreHead = f"#F#{len(gui.data.fre_IDs):04d}\n"
                self.ser.write(FreHead.encode())
                self.FrequencyID_UART_TX(gui)
                FreTail = "#P#\n"
                self.ser.write(FreTail.encode())
            elif self.SerState  == "MXStart":
                self.ser.write(gui.data.Start_out.encode())
                gui.data.radio_test_data = []
                gui.data.saved_data = []
                gui.data.data_error_count = 0
            elif self.SerState == "TimeRqst":
                gui.data.TimeGeneration()
                self.ser.write(gui.data.TimeRes.encode())
            elif self.SerState == "RandomRqst":
                gui.data.RandomNumberGeneration()
                self.ser.write(gui.data.random_radio.encode())
            elif self.SerState == "DataRec":
                gui.data.SaveRadioData()
            elif self.SerState == "MXStop":
                gui.node_status_txt["text"] = "Node Status"
                gui.node_status["text"] = "Node collection complete."
                gui.node_status["fg"] = "green"
                
                gui.collection_ctrl()
                
                self.threading = False
            elif self.SerState == "WaitforMCU":
                pass
            
            if self.threading:
                if self.ser.is_open: 
                    while self.ser.in_waiting == 0: 
                        if not self.threading: break
                        time.sleep(0.01)
                        if not self.threading: break
                
                if not self.threading: break 
            
                gui.data.RowMsg = self.ser.readline()
                gui.logger.logger.insert(tk.END, gui.data.RowMsg)
                if gui.logger.auto_scroll.get():
                    gui.logger.logger.see(tk.END)
                
                gui.data.DecodeMsg()
                
                if gui.data.WID_done:
                    self.SerState = "TXFreIDs"
                if gui.data.fre_rec:
                    self.SerState = "MXStart"
                if gui.data.t_rqst_ok:
                    gui.data.radio_cmd = int(gui.data.msg[2])
                    self.SerState = "TimeRqst"
                if gui.data.random_ok:
                    #print("here")
                    gui.data.random_num_len = int(gui.data.msg[1])
                    #print(gui.data.random_num_len)
                    gui.data.radio_cmd = int(gui.data.msg[2])
                    #print(gui.data.radio_cmd)
                    self.SerState = "RandomRqst"
                if gui.data.St_tlk_ok:
                    gui.node_status_txt["text"] = f"Node {gui.data.current_node} Status"
                    gui.node_status["text"] = "Pending..."
                    gui.node_status["fg"] = "orange"
                    gui.ACK_status["text"] = "Pending..."
                    gui.ACK_status["fg"] = "orange"
                    gui.time_cal_status["text"] = "Pending..."
                    gui.time_cal_status["fg"] = "orange"
                    gui.freID_status["text"] = "Pending..."
                    gui.freID_status["fg"] = "orange"
                    gui.data_rec_status["text"] = "Pending..."
                    gui.data_rec_status["fg"] = "orange"
                    gui.data_save_status["text"] = "Pending..."
                    gui.data_save_status["fg"] = "orange"
                    self.SerState = "WaitforMCU"
                if gui.data.node_done_flag :
                    
                    gui.data.nodes[gui.data.msg[1]] = 'Done'
                    sensordnIDs = [key for key, value in gui.data.nodes.items() 
                                            if value == 'Done']
                    if not sensordnIDs:
                        gui.complete_nodes["text"] = "None"
                        gui.complete_nodes["fg"] = "black"
                    else:
                        gui.complete_nodes["text"] = ', '.join(sensordnIDs)
                        gui.complete_nodes["fg"] = "green"
                        
                    done_txt = "#W#\n"
                        
                    self.ser.write(done_txt.encode())
                        
                    self.SerState = "WaitforMCU"
                if gui.data.Info_display:
                    self.SerState = "WaitforMCU"
                    if 'FreLenNotMactched' in gui.data.msg[1] or 'IDsLenNotMactched' in gui.data.msg[1]:
                        ErrorMsg = f"UART Transmission Error: {gui.data.msg[1]}"
                        messagebox.showerror("error", ErrorMsg)
                        
                        gui.collection_ctrl()
                        
                        self.threading = False
                    if(len(gui.data.msg)>2):
                        if 'Waking up' in gui.data.msg[2]:
                            gui.node_status["text"] = "Waking up the sensor..."
                            gui.node_status["fg"] = "green"
                        elif 'Collecting data' in gui.data.msg[2]:
                            gui.node_status["text"] = "Collecting data..."
                            gui.node_status["fg"] = "green"
                        elif 'CMD timeout' in gui.data.msg[2]:
                            gui.node_status["text"] = "CMD wait timeout."
                            gui.node_status["fg"] = "red"
                        elif 'DATA timeout' in gui.data.msg[2]:
                            gui.node_status["text"] = "Data wait timeout."
                            gui.node_status["fg"] = "red"
                        elif 'TimeCalFailed' in gui.data.msg[2]:
                            gui.time_cal_status["text"] = \
                                f"{gui.data.msg[3]} times failed"
                            gui.time_cal_status["fg"] = "red" 
                            gui.node_status["text"] = "Time calibration failed"
                            gui.node_status["fg"] = "red"
                        elif 'ResendFailed' in gui.data.msg[2]:
                            gui.data_rec_status["text"] = \
                                f"Resend {gui.data.msg[3]} times failed"
                            gui.data_rec_status["fg"] = "red"
                            gui.node_status["text"] = "Saved data with errors"
                            gui.node_status["fg"] = "red"
                        elif 'Calibrating time' in gui.data.msg[2]:
                            gui.node_status["text"] = "Calibrating time..."
                            gui.node_status["fg"] = "green"
                        elif 'Sending FreIDs' in gui.data.msg[2]:
                            gui.node_status["text"] = "Sending Fre.IDs to radio..."
                            gui.node_status["fg"] = "green"
                        elif 'TimeMatched' in gui.data.msg[2]:
                            gui.time_cal_status["text"] = "Yes"
                            gui.time_cal_status["fg"] = "green" 
                            gui.data.radio_test_data.append(gui.data.time_to_Radio)
                        elif 'FreIDsTXOK' in gui.data.msg[2]:
                            gui.freID_status["text"] = "UG nodes received OK"
                            gui.freID_status["fg"] = "green"
                        elif'FreIDsFailed' in gui.data.msg[2]:
                            gui.freID_status["text"] = \
                                f"{gui.data.msg[3]} times failed"
                            gui.freID_status["fg"] = "orange"
                            gui.node_status["text"] = "Fre IDs. TX failed"
                            gui.node_status["fg"] = "red"
                        elif 'NodeStop' in gui.data.msg[2]:
                            self.SerState = "MXStart"
                        elif 'AllDone' in gui.data.msg[2]:
                            self.SerState = "MXStop"
                        elif 'AKReceived' in gui.data.msg[2]:
                            gui.ACK_status["text"] = "Yes"
                            gui.ACK_status["fg"] = "green"
                         
                if gui.data.Received_data:
                    if(len(gui.data.msg)>2):
                        if 'Recdata' in gui.data.msg[2]:
                            gui.data.Data_len = int(gui.data.msg[3])
                            gui.data_rec_status["text"] = "Yes"
                            gui.data_rec_status["fg"] = "green"
                            self.SerState = "WaitforMCU"
                        elif 'Savedata' in gui.data.msg[2]:
                            gui.node_status["text"] = "Saving received data..."
                            gui.node_status["fg"] = "green"
                            self.SerState = "DataRec"
                        elif 'DataNoErrors' in gui.data.msg[2]:
                            gui.data_rec_status["text"] = "Yes, no errors."
                            gui.data_rec_status["fg"] = "green"
                            gui.node_status["text"] = "Saving to file."
                            gui.node_status["fg"] = "green"
                            gui.data.RadioDataToFile()
                            
                            fre, mag_dB, phs_deg = gui.plot.calculate_freq_mag_phase(gui.data.fre_id_rec, 
                                                                                     gui.data.mag, 
                                                                                     gui.data.phs)
                            label = gui.plot.create_label(gui.data.filename1, '.csv')
                            gui.plot.update_plot(fre, mag_dB, phs_deg, label) 
        
                            # make sure saving data is successful
                            if gui.data.data_save_ok: 
                                gui.data_save_status["text"] = "Yes"
                                gui.data_save_status["fg"] = "green"
                                gui.node_status["text"] = "Data saved to file."
                                gui.node_status["fg"] = "green"
                            else: 
                                # print("Error saving file")
                                gui.node_status["text"] = "Error saving file."
                                gui.node_status["fg"] = "red"
                            self.SerState = "WaitforMCU"
                        elif 'DataWithErrors' in gui.data.msg[2]:
                            gui.data_rec_status["text"] = "Yes,with errors"
                            gui.data_rec_status["fg"] = "red"
                            gui.node_status["text"] = "Requesting to resend..."
                            gui.node_status["fg"] = "green"
                            
                            gui.data.data_error_count+=1
                            gui.data.RadioDataToFile()
                            # make sure saving data is successful
                            if gui.data.data_save_ok: 
                                gui.node_status["text"] = "Error data saved to file."
                                gui.node_status["fg"] = "green" 
                                 
                            else: 
                                # print("Error saving file")
                                gui.node_status["text"] = "Error data saving failed."
                                gui.node_status["fg"] = "red"
                            self.SerState = "WaitforMCU"
                        elif 'WrongLength' in gui.data.msg[2]:
                            # print(f"Recived:{gui.data.Data_len} Expected:{gui.data.msg[3]}")
                            gui.data_rec_status["text"] = "Yes,wrong length"
                            gui.data_rec_status["fg"] = "red"
                            gui.node_status["text"] = "Requesting to resend..."
                            gui.node_status["fg"] = "green"
                            
                            gui.data.data_error_count+=1
                            gui.data.RadioDataToFile()
                            # make sure saving data is successful
                            if gui.data.data_save_ok: 
                                gui.node_status["text"] = "Error data saved to file."
                                gui.node_status["fg"] = "green" 
                                 
                            else: 
                                # print("Error saving file")
                                gui.node_status["text"] = "Error data saving failed."
                                gui.node_status["fg"] = "red"
                            self.SerState = "WaitforMCU"
                
                                
                                
if __name__ == "__main__":
    SerialCtrl()
