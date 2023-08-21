

import pathlib 
import os
import re
import pandas as pd

class Parser:
    def __init__(self, filename, config_file, excel_name):
        self.filename = filename  
        self.config_file = config_file
        self.excel = excel_name
        self.pattern = re.compile(r'\{([^}]*)\}')
        self.irrelevant_info_pattern = re.compile(r'(\w+|[0-9])\s*(\(\w+\))')
        self.complex_pattern = re.compile(r'(Option\s*:?\s*(?:no|\#)\d+:?\s*\w+\s*[!=]=\s*\{[^}]*\})')
        self.option_number_pattern = re.compile(r'[O|o]p[rt]ion\s*:?\s*(?:no|\#)?\s*\d+')
        self.replace_option_number = re.compile(r'[Oo]p[tr]ion\s*:?\s*(?:no|\#)?\s*\d+\s*:?\s*(?:\w+\s*)+')
        self.parsed_config_pattern = re.compile(r'Parsed\s*Config\s*:?\s*(\w+)')

    def expected_results(self): 
        #A list of dictionaries that will keep track of the expected result of each Slot # and Chl#
        results = []
        parsed_config = None
        config = self.config()
        #Dictionary: Key is option number
        #List of dictionaries containing all info of each Slot# and Chl#
        data = self.ICD()  
       # print(data)
        if self.excel: 
            self.PP_Specs = parse_PP_Spec(self.excel, self.config_file)
            parsed_config = self.PP_Specs.process_excel()
        #Iterate through the data 
        for e in data: 
            if "Config" in e and "Signal desc" in e and "IO" in e: 
                list_of_cnd = []
                add = {}

                if len(e["Signal desc"]) == len(e["Config"]) and len(e["Signal desc"]) == len(e["IO"]): 
                    add["Slot"] = e["Slot #"]
                    add["Chl"] = e["Chl #"]
                    add["IO"] = e["IO"]
                   
                    value, desc = False, ""
                    for conditional in e["Config"]: 
                        #Returns a boolean
                        res, cond = self.evaluate(conditional, parsed_config, config)
                        list_of_cnd.append(cond)
                       # print(res)
                       #If there is more than one IO that is passing, immediately mark it as a fail
                        if value and res is not False:
                          
                            add[e["Signal desc"].pop(0)] = 'Fail'
                            add[desc] = 'Fail'
                        else:
                            if res is not False:
                                name = e["Signal desc"].pop(0)
                                add[name] = 'Active'
                                value, desc = True, name
                    
                            elif res == False:
                                add[e["Signal desc"].pop(0)] = 'Not Active'

                    add["Configurables"] = list_of_cnd
                    results.append(add)
        return results

    def config(self): 
        file = self.config_file + ".txt"
        file = file.split("/")[-1]
        path = self.find_file_path(file)
        readfile = open(path, "r")
        # (Key) Option # => [Loco Option, Value, (If included) range]
        data = {}
        
        for l in readfile.readlines(): 
            #looks for lines such as 007 : Engine_Type = GEVO12_HPCR_T4
            match = re.search(r'(\d{3}) : (\w+) = (\w+)', l)
            #Similar but looks for a * instead of a :
            has_range = re.search(r'(\d{3}) \* (\w+) = (\d+.\d+)\s+R \[(\d+.\d+ \d+.\d+)\]', l)
            if match:
                data[match.group(1)] =  [match.group(2), match.group(3)]
            elif has_range: 
                r = has_range.group(4).split(" ")
                data[has_range.group(1)] =  [has_range.group(2), has_range.group(3), r]
        
        readfile.close()

        return data

    def evaluate(self, expr, config_params, data): 
        r = False
  
        #Removes any extra spaces, unknown ascii, number ordering (e.g. 1.) hello becomes hello)
        #Adds a == for every = in the string 
        expr = self.preprocess_expression(expr)
        #If there is a Note instead of a conditional immediately return 
        if re.search(r'\s*\([Nn]ote', expr):
            return False, expr
        #Takes a list of all the option numbers found in the string 
        option_numbers = self.option_number_pattern.findall(expr)
      
        #Looks for any parsed config parameters 
        parsed_config = self.parsed_config_pattern.findall(expr)
     
        #As an example, takes 007 from Option 007
        values = self.retrieve_option_values(option_numbers, data)

        if values:
            if config_params:
                expr = self.replace_parsed_config(expr, config_params)
            #From Option 007 : Engine_Type == GEVO12_HPCR_T4 it will become xyz3 ==  GEVO12_HPCR_T4
            expr = self.replace_option_values(expr, values)

            expr = self.process_expression(expr)
          
            try:
                #evaluates the string 
                r = eval(expr)
            except:
                return False, expr
        return r, expr
    #Removes any character that could be a possible edge case
    def preprocess_expression(self, expr):
        expr = re.sub(r'\s+', ' ', expr)
        expr = re.sub(r'\d+.\)', ' ', expr)
        expr = re.sub(r'\.', ' ', expr)
        expr = re.sub(r'[^\x00-\x7F]', '', expr)
        irrelevant_info = self.irrelevant_info_pattern.search(expr)
        if irrelevant_info:
            expr = re.sub(r"\s*(\(\w+)\)", ' ', expr)
        expr = re.sub(r'!\s*=', '!=', expr)
        expr = re.sub(r'(?<!\!)=(?!=)', '==', expr)
        return expr
    
    #Replaces any string that starts with Parsed config
    def replace_parsed_config(self, expr, config_params):
        for p in self.parsed_config_pattern.findall(expr):
            for row in config_params:
                if p in row:
                    expr = re.sub(r'Parsed\s*Config\s*:?\s*\w+', row[3], expr)
        return expr
    
    #Uses the config file to lookup the values depending on the option number
    def retrieve_option_values(self, option_numbers, data):
        values = []
      #  print(option_numbers)
        for number in option_numbers:
            
            k = re.findall(r'\d+', number)[0]
            #print(k)
            if k.zfill(3) in data:
              #  print('NO')
                values.append(data[k.zfill(3)][1])
            else:
                return []
        return values
    
    #Replaces any strings that start with 'Option 123: xyv' with it's corresponding value
    def replace_option_values(self, expr, values):
        expr = self.replace_option_number.sub(lambda match: str(values.pop(0)), expr)
        return expr
    #Used so that the string can be evaluated using the eval()
    def process_expression(self, expr):
        expr = re.sub(r'(\w+\([^)]*\)?)|(\w+)', r"'\1\2'", expr)
        expr = expr.lower()
        expr = re.sub(r'===', '==', expr)
        expr = re.sub(r'\'and\'', 'and', expr)
        expr = re.sub(r'\'or\'', 'or', expr)
        expr = re.sub(r'\{|\}|\(|\)', '', expr)
        return expr


    def ICD(self): 
        path = self.find_file_path(self.filename)
        r = open(path, "r", encoding = 'UTF8')
     
        #Keep track of which line we are parsing 
        line = r.readline()
        # 4 = Signal desc, 5 = IO, 6 = Software Specs, 7 = Configs, 8 = Default/Slope, 9 = Pub Rate/Offset, 
        # 10 = Active State/Default, 11 = OC Retry Timer/Debounce/Publication Rate, 12 = OC Fail Counter/Owner spec, 13 = OC Incident, 14 = Specification 
        index = 4
        #Have a list of dictionaries
        #The row will hold 
        # [Slot#, Chl#, Type, Signal Description, IO Manager Software Name, Configurable, Default, 
        # Pub Rate, Active State, OC Retry Timer, OC fail Counter, OC Incident, Specification]
        table = []
      
        #Keep populating until you see another signal type
        while line:
             has_crd_chl = re.search(r'^\s*(\d+)-(\d{1,3})$', line)
             
             dictionary = {}
             if has_crd_chl:
                 
                #Accumalates all the info for its Slot# and Chl#
                dictionary["Slot #"] = has_crd_chl.group(1)
                dictionary["Chl #"] = has_crd_chl.group(2)
                
                
                line = r.readline()
                line = self.skip_new_line(line, r)

                has_type = re.search(r'^\s*([A-Z]+)$', line)
                
                if has_type: 
                    #Grab type 
                    dictionary["Type"] = has_type.group(1)
                    line = r.readline()
                    line = self.skip_new_line(line, r)

                    #Searches for lines like 1.) blaeh
                    other = re.search(r'\d+\.?\)?(.+)', line)
                    
                    if other:  
                        while index <= 14:
                            match index: 
                                case 4: 
                                    #Check for continuations
                                    line = self.add("Signal desc", line, dictionary, r)
                                    line = self.skip_new_line(line, r)
                                case 5:
                                    line = self.add("IO", line, dictionary, r)               
                                    line = self.skip_new_line(line, r)
                                case 6: 
                                    line = self.add("Software Specs", line, dictionary, r)
                                    line = self.skip_new_line(line, r)
                                case 7: 
                                    line = self.add("Config", line, dictionary, r)
                                    line = self.skip_new_line(line, r) 
                                case 8: 
                                    line = self.add(8, line, dictionary, r)                                 
                                case 9: 
                                    line = self.add(9, line, dictionary, r)                                  
                                case 10: 
                                    line = self.add(10, line, dictionary, r)                                 
                                case 11: 
                                    line = self.add(11, line, dictionary, r)                                    
                                case 12: 
                                    line = self.add(12, line, dictionary, r)                                  
                                case 13: 
                                    line = self.add(13, line, dictionary, r)                                
                                case 14: 
                                    line = self.add(14, line, dictionary, r)
                                  
                            index += 1   
                        #Reset the index
                        index = 4
                        #Add the dictionary to the list
                    else:
                        spare = re.search(r'(.+)', line)
             
                        dictionary["spare"] = spare.group(1).strip()

                    table.append(dictionary) 
              
             line = r.readline()
        r.close() 
        return table

    #Keeps reading an ongoing conditional rp 
    def skip_new_line(self, l, file): 
        while l == '\n' or not(l.strip()) or l == 'r\n': 
            l = file.readline()
        
        return l

    def add(self, key, line, dicti, filename): 

         current_item = None

         while line.strip():
                desc = re.search(r'^\s*\(?\d+\.\)(.+)', line)
                desc1 = re.search(r'^\s*\(?\d+\.\)?(.+)', line)
                desc2 = re.search(r'^\s*\(?\d+\.?\)(.+)', line)
               
               
                if desc or desc1 or desc2:
 
                    if current_item is not None:
                        dicti.setdefault(key, []).append(current_item) 
                    if desc:
                        current_item = desc.group(1).strip()  
                    elif desc1: 
                        current_item = desc1.group(1).strip() 
                    elif desc1: 
                        current_item = desc2.group(1).strip() 

                else:             
                    if current_item is not None:
                        current_item += " " + line.strip()
                       
                line = filename.readline()

         if current_item is not None:
            dicti.setdefault(key, []).append(current_item)

         return line

    #finds the absolute filepath based on the filename
    #Note: Thise code will run faster if you placed all files in one directory and provide the file path here
    #Much better than starting the root
    def find_file_path(self, name): 
        for root, dirs, files in os.walk('/'): 
            if name in files: 
                return os.path.abspath(os.path.join(root, name))
        return None


    def help_parse_conditional(self, cond):
        complex_pattern = re.compile(r'([Oo]ption\s*(?:no)?\s*\d{3}:?[^=]+(?:==?)[^()]+)')
    
        complex_match = complex_pattern.findall(cond)

        comp_pattern2 = re.compile(r'\b(?:\w+\s+(?:and|or)\s+(?!Option\s+\d+:\s+\w+\s*=.+)\w+\s*)+\b')
        compl = comp_pattern2.search(cond)

        other_opt = re.search(r'(\w+)\s*\(([Oo]ption)\s*(\d+):?\)\s*([!=]=)?\s*(\w+)', cond)

        if complex_match:
            
                    option = re.search(r'([Oo]ption\s*(?:no)?\s*\d{3}\s*:?[^=]+(?:==?))', cond)
               
                    between = re.search(r'[Oo]ption\s*(?:no)?\s*\d{3}:?[^=]+(?:==?)\s*((?:{[^{}]+}|[^{}()]+))', cond)
                  
                    cond = complex_pattern.sub(between.group(1), cond)
                   
                   # print(val)
                    val = re.sub(r'\b(?!or|OR|and|AND\b)(\w+)\b', option.group(0) + r' \1', cond)
                  
                    cond = val
        elif other_opt:
            s = f"{other_opt.group(2)} {other_opt.group(3)} {other_opt.group(1)} {other_opt.group(4)} {other_opt.group(5)}"
            return s

        return cond


class parse_PP_Spec: 
    def __init__(self, excel_name, config): 
        self.name = excel_name
        self.parser_object = Parser("DOORS.txt", config, None)

    def process_excel(self): 
        filepath = self.parser_object.find_file_path(self.name)
        table = []
        data = pd.read_excel(filepath)
        config = self.parser_object.config()
        #Set the first column as the index of for all the rows in the 2D arr
        data = data.set_index(data.columns[0])
        #Convert DataFrame to a 2D list 
        data_list = data.values.tolist()
      
       #Iterate throught each row and evaluate the conditional
        for row in data_list:  
            #Check if pandas gave a nan value
            if not(pd.isna(row[3])):
              
                value  = self.parse_conditional(row[3], config)
               
                row[3] = value
                table.append(row)
            

      #  print(table)
        return table

    def parse_conditional(self, cond, data):        
       # Remove newlines and tabs

        cond = re.sub(r'[\n\t]', ' ', cond)
        cond = re.sub(r'! =', '!=', cond)

    # Pattern for extracting conditionals and values
        pattern = re.compile(r"(?:(\w+ = \w+);)?\s*(?i:\bIF\b)\s*(.*?)\s*(?i:\bTHEN\b)\s*(.*?)\s*(?:(?i:\bELSE\s*IF\b)\s*(.*?)\s*(?i:THEN)\s*(.*?)\s*)*(?:(?i:\bELSE\b)\s*(.*?)$|$)")
        matches = pattern.search(cond)

        if matches:
            l = matches.groups()
            groups = [x for x in l if x is not None]
            value = r'\w+ [=]=? (\w+);?'
         
            if_cond = groups[0]
            if_value = groups[1]

        # Evaluate the IF condition
        
            if_cond = self.parser_object.help_parse_conditional(if_cond)
          
            if_res = self.parser_object.evaluate(if_cond, None, data)
            
            if if_res:
          
                res = re.search(value, if_value)
                if res: 
                    return res.group(1) 
            else:
            # Iterate through the else if conditions and evaluate them
                for i in range(2, len(groups), 2):
                    elif_cond = groups[i]
              
                    expr = re.search(r'\w+ [=!]=? \w+', elif_cond)
                    if_res = False
              
                    if (i + 1) < len(groups) and expr:
                        elif_cond = groups[i]
                        elif_val = groups[i + 1]
                      
                        elif_cond = self.parser_object.help_parse_conditional(elif_cond)
                        elif_res = self.parser_object.evaluate(elif_cond, None, data)
                     #   print(elif_res)
                        if elif_res:
                          
                            res = re.search(value, elif_val)
                            return res.group(1)
                    elif elif_cond == groups[-1]: 
                   
                        res = re.search(value, elif_cond)
                        return res.group(1)
        return None
