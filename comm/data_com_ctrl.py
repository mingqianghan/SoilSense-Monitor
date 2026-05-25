# -*- coding: utf-8 -*-
"""
Created on Sat Apr 27 20:45:50 2024

@author: mingqiang
"""

from datetime import datetime
import os
import random
import pandas as pd
import numpy as np

class DataMaster():
    def __init__(self):
        self.sync_out = "#?#\n"
        self.sync_in = "!"
        self.Start_out = "#A#\n"
        self.disconnect_out = "#H#\n"
        self.Time_rqst = "T"
        self.Data_in = "D"
        self.random_rqst ="R"
        self.Info_in = "I"
        self.St_talking = "S"
        self.Fre_ID_done = "Y"
        self.WID_done = "Z"
        self.node_done = "W"
        
        self.config = []
        self.nodes = {}
        self.fre_IDs = []
        self.working_nodes = []
        self.sync_ok = False
        self.WID_ok = False
        self.saved_data = []
        self.msg = []
        self.random_radio = []
        self.radio_test_data = []
        self.fre_id_rec = []
        self.mag = []
        self.phs = []
        self.data_error_count = 0
        self.random_num_len = 0
        self.radio_cmd = 0
        self.time_to_Radio = None
        self.data_save_ok = False
        self.TimeRes = None
        self.Data_len = None
        self.random_ok = False
        self.current_node = None
        self.Info_display = False
        self.Received_data = False
        self.St_tlk_ok = False
        self.t_rqst_ok = False
        self.fre_rec = False
        self.node_done_flag = False
        
        
    def DecodeMsg(self):
        # self.sync_ok = False
        self.t_rqst_ok = False
        self.random_ok = False
        self.Info_display = False
        self.Received_data = False
        self.St_tlk_ok = False
        self.fre_rec = False
        self.node_done_flag = False
        
        temp = self.RowMsg.decode('utf8') 
        if "#" in temp: 
            self.msg = temp.split("#")
            # print(f"Before removing index :{self.msg}")
            del self.msg[0]
            # print(f"After removing index :{self.msg}")
            if(self.sync_in in self.msg[0]): 
                self.sync_ok = True
            if(self.WID_done in self.msg[0]):
                self.WID_ok = True
            if(self.Fre_ID_done in self.msg[0]):
                self.fre_rec = True
            if(self.St_talking in self.msg[0]):
                self.St_tlk_ok = True
                self.current_node = int(self.msg[1])
            if(self.Time_rqst in self.msg[0]):
                self.t_rqst_ok = True
            if(self.random_rqst in self.msg[0]):
                self.random_ok = True
            if(self.Info_in in self.msg[0]):
                self.Info_display = True
            if(self.Data_in in self.msg[0]):
                self.Received_data = True
            if(self.node_done in self.msg[0]):
                self.node_done_flag = True
                        
                
    def TimeGeneration(self):
        now = datetime.now()
        self.TimeRes = (f"#M#{(now.year)%100:02d}_"
                        f"{now.month:02d}_"
                        f"{now.day:02d}_"
                        f"{(now.weekday())+1:02d}_"
                        f"{now.hour:02d}_"
                       f"{now.minute:02d}_"
                       f"{now.second:02d}#\n")
        self.time_to_Radio = [self.radio_cmd, self.current_node,
                              (now.year)%100, now.month, now.day, 
                              now.weekday()+1, now.hour, now.minute,
                              now.second]
        #print( self.time_to_Radio)
        # print(self.TimeRes)
        
    def RandomNumberGeneration(self):
        random_numbers = [random.randint(0, 255) 
                          for _ in range(self.random_num_len)]
        #print(random_numbers)
        
        test_data = [self.radio_cmd, self.current_node] + random_numbers
        self.radio_test_data.append(test_data)
        #print(test_data)
        
        self.random_radio = "#N#"
        for number in random_numbers:
            self.random_radio += f"{number:03d}"
        self.random_radio += "#\n"
        
        #print(self.random_radio)

        
    def SaveRadioData(self):
        if len(self.msg)>3 and self.msg[3]: 
            self.saved_data.append(self.msg[3])
            
            
    def RadioDataToFile(self):
        now = datetime.now()

        # Base directory — overridable via self.save_root (set from config.json
        # by AppRoot). Falls back to the legacy relative folder when unset.
        base_directory = getattr(self, "save_root", None) or "data\\UG nodes"
        # Subdirectory for the current node
        node_directory = os.path.join(base_directory, f"{self.current_node}")
        
        # Check if the node-specific subdirectory exists, 
        # and create it if it doesn't
        if not os.path.exists(node_directory): 
            os.makedirs(node_directory)
            
        self.filename1 = (f"d{self.current_node}-"
                          f"{(now.year)%100:02d}_"
                          f"{now.month:02d}_"
                          f"{now.day:02d}-"
                          f"{now.hour:02d}_"
                          f"{now.minute:02d}_"
                          f"{now.second:02d}.csv")
        
        filename2 = (f"r{self.current_node}-"
                    f"{(now.year)%100:02d}_"
                    f"{now.month:02d}_"
                    f"{now.day:02d}-"
                    f"{now.hour:02d}_"
                    f"{now.minute:02d}_"
                    f"{now.second:02d}.csv")
        
        if(self.data_error_count>0): 
            self.filename1 = (f"d{self.current_node}-"
                              f"{(now.year)%100:02d}_"
                              f"{now.month:02d}_"
                              f"{now.day:02d}-"
                              f"{now.hour:02d}_"
                              f"{now.minute:02d}_"
                              f"{now.second:02d}(ve{self.data_error_count}).csv")  
        else: 
            self.filename1 = (f"d{self.current_node}-"
                              f"{(now.year)%100:02d}_"
                              f"{now.month:02d}_"
                              f"{now.day:02d}-"
                              f"{now.hour:02d}_"
                              f"{now.minute:02d}_"
                              f"{now.second:02d}(wo).csv")  
            
        
        # Complete path includes the node-specific subdirectory
        complete_path1 = os.path.join(node_directory, self.filename1)
        complete_path2 = os.path.join(node_directory, filename2)
      
        # Define data types for each column
        column_types1 = {'fre_idx': int, 'mag (dig)': int, 
                         'mag_m(V)': float, 'phs (dig)': int,
                         'phs_m(V)': float, 'parity': int,
                        'RSSI(dBm)': int, 'SNR (dB)': int}


        # Create DataFrame with specified data types
        df_sensor_data = pd.DataFrame([x.split() for x in self.saved_data], 
                                      columns=['fre_idx', 'mag (dig)',
                                             'mag_m(V)', 'phs (dig)',
                                             'phs_m(V)', 'parity',
                                             'RSSI(dBm)', 
                                             'SNR (dB)']).astype(column_types1)
        
        self.mag = df_sensor_data['mag (dig)']
        self.phs = df_sensor_data['phs (dig)']
        self.fre_id_rec = df_sensor_data['fre_idx']
        
        df_radio_data = pd.DataFrame(self.radio_test_data)
        df_radio_data = df_radio_data.astype(int)

        try: 
            df_sensor_data.to_csv(complete_path1, index=False)
            try: 
                saved_df = pd.read_csv(complete_path1)
                # print("Read number of rows:", saved_df.shape[0])
                # print("Expected number of rows:", self.Data_len)
                if (saved_df.shape[0] == self.Data_len):
                    self.data_save_ok = True
                else:
                    self.data_save_ok = False  
            except Exception as e:
                self.data_save_ok = False
                # print("Data length does not match: f{e}")
        except Exception as e:
            self.data_save_ok = False
            # print(f"Error saving file: {e}")
        
        # print( self.data_save_ok )
        if self.data_save_ok:
            if self.data_error_count<=1: 
                try: 
                    df_radio_data.to_csv(complete_path2, 
                                         header=False, index=False)
                    try: 
                        saved_df = pd.read_csv(complete_path2, header=None)
                        # print("Read number of rows:", saved_df.shape[0])
                        # print("Expected number of rows:", self.Data_len)
                        if (saved_df.shape[0] == 3):
                            self.data_save_ok = True
                        else:
                            self.data_save_ok = False
                    except Exception as e:
                        self.data_save_ok = False
                        # print("Data length does not match: f{e}")
                except Exception as e:
                    self.data_save_ok = False
        # print( self.data_save_ok )
        self.saved_data = []
                
    def ClearData(self):
        self.fre_IDs = []
        self.saved_data = []
        self.msg = []
        self.SiteName = None
        self.SiteLatitude = None
        self.SiteLongitude = None
        self.sensorIDs = []
        self.random_radio = []
        self.radio_test_data = []
        self.mag = []
        self.phs = []
        self.data_error_count = 0
        self.random_num_len = 0
        self.radio_cmd = 0
        self.time_to_Radio = None
        self.data_save_ok = False
        self.TimeRes = None
        self.Data_len = None
        self.sync_ok = False
        self.random_ok = False
        self.current_node = None
        self.Info_display = False
        self.Received_data = False
        self.St_tlk_ok = False
        self.t_rqst_ok = False
        self.node_done_flag = False
                       
