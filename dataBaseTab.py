from typing import List, Dict, Optional

import PySimpleGUI as sg
import configparser
from datetime import date
import datetime
import tkcalendar

import requests
import lxml.html as lh

import berserk
import berserk.utils
import berserk.exceptions

import os
import json

MAX_PGN_FILE_SIZE = 5000000  # 5MB?
PGN_SIZE_PER_GAME = 800


## class for search result in choosen database
class DataBaseSearchResult:
    filename: str
    fromDate: date
    tillDate: date

    def __init__(self, filename: str, fromDate: date, tillDate: date):
        self.filename = filename
        self.fromDate = fromDate
        self.tillDate = tillDate


## class for current operation evaluation
class Operation:
    operationName: str
    max_value: int

    def __init__(self, operationName, max_value):
        self.operationName = operationName
        self.max_value = max_value

    def __enter__(self):
        sg.one_line_progress_meter(title=self.operationName,
                                   current_value=0,
                                   max_value=self.max_value,
                                   orientation='h',
                                   bar_color=(None, None),
                                   button_color=None,
                                   size=(20, 20),
                                   grab_anywhere=False,
                                   no_titlebar=False,
                                   key='_db_progress_')
        return self

    def update(self, value: int):
        sg.one_line_progress_meter(title=self.operationName,
                                   current_value=value if value < self.max_value else self.max_value,
                                   max_value=self.max_value,
                                   orientation='h',
                                   bar_color=(None, None),
                                   button_color=None,
                                   size=(20, 20),
                                   grab_anywhere=False,
                                   no_titlebar=False,
                                   key='_db_progress_')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sg.one_line_progress_meter(title=self.operationName,
                                   max_value=self.max_value,
                                   key='_db_progress_',
                                   current_value=self.max_value)


## returns months range between two given dates
def getMonthRange(startDate: date, endDate: date) -> List[date]:
    month = startDate.month
    year = startDate.year
    result = []
    while datetime.date(year, month, 1) <= endDate:
        result.append(date(year, month, 1))
        month += 1
        if month > 12:
            year += 1
            month = 1
    return result


# main class
class DatabaseTab:
    config: configparser.RawConfigParser  # configuration
    databases: List[str]  # list of avaliable databases
    searchTableHeadingsSizes: Dict[str, int]  # sizes of search table columns if search gave multiple results
    searchTableIdIndex: int  # index of id entry in search table
    lichessClient: Optional[berserk.Client]  # client for lichess database
    from_calendar: Optional[tkcalendar.DateEntry]  # from date tkinter widget
    till_calendar: Optional[tkcalendar.DateEntry]  # till date tkinter widget

    def __init__(self, configFile):
        self.databaseTab: sg.Frame  # database frame
        self.databaseFindFunctions: Dict[str, callable]  # map from database name to function performs search in it

        self.config = configparser.RawConfigParser()
        self.config.read(configFile)
        self.databases = self.config.get('databases', 'databases').split(',')
        self.searchTableHeadingsSizes = {'#': 3, 'Id': 8, 'Name': 20, 'Title': 4, 'Elo': 4}
        self.searchTableIdIndex = 1
        self.databaseTab = sg.Frame(title='Database', layout=[
            [sg.Text('Database:', size=(8, 1)),
             sg.Combo(self.databases, default_value=self.config.get('databases', 'default'), key='_db_name_'),
             sg.Text('Name:', size=(8, 1)), sg.InputText(key='_db_name_input_', size=(23, 1)),
             sg.Text('From date: '), sg.Column([[]], key='_db_from_frame_'),
             sg.Text('Till date: '), sg.Column([[]], key='_db_till_frame_'),
             sg.Button('Find', key='_db_find_')]])
        self.databaseFindFunctions = {
            'chess-db': lambda window, name, fromDate, tillDate: self.chessDbFind(window, name),
            'lichess': lambda window, name, fromDate, tillDate: self.lichessDbFind(name, fromDate, tillDate),
            'chess.com': lambda window, name, fromDate, tillDate: self.chesscomDbFind(name, fromDate, tillDate)
        }
        self.from_calendar = None
        self.till_calendar = None

        self.lichessClient = None

    #################################################### Helpers #######################################################
    ## returns tab
    def getTab(self) -> sg.Frame:
        return self.databaseTab

    ## Starts operation
    @staticmethod
    def startOperation(operation: str, max_value: int = 100) -> Operation:
        return Operation(operation, max_value)

    ################################################### chess-db #######################################################
    ## In case find in chess-db gives not uniq results shows them in the table downloads pgn file from given url
    def chessDbDownloadFile(self,
                            htmlSession: requests.Session,
                            downloadURL: str,
                            sizeEstimation: int) -> Optional[str]:

        filename = sg.PopupGetFile('Save Game', title='Save Game', no_window=True, default_extension='pgn',
                                   save_as=True, file_types=(('PGN Files', '*.pgn'),))
        if filename == '':
            return None
        try:

            response = htmlSession.get(url=downloadURL, stream=True)
            filesize = MAX_PGN_FILE_SIZE if (sizeEstimation is None) else sizeEstimation

            with self.startOperation('Downloading', filesize) as operation:
                dowloadedSize = 0
                lastUpdatedSize = 0
                with open(filename, 'wb') as f:
                    for ch in response:
                        f.write(ch)
                        dowloadedSize += len(ch)
                        # update once per 1%
                        if dowloadedSize - lastUpdatedSize > filesize / 100:
                            lastUpdatedSize = dowloadedSize
                            value = dowloadedSize if (dowloadedSize < filesize) else filesize - 1
                            operation.update(value)
        except:
            sg.PopupError('Unable to connect chess-db', title='ERROR')
            return None

        return filename

    ## shows search list if name is non-uniq
    def chessDbShowSearchList(self, window: sg.Window, doc: lh.HtmlElement) -> None:
        th_elements = doc.xpath('//font/table/tr/th')
        tr_elements = doc.xpath('//font/table/tr')
        if len(th_elements) == 0:
            sg.PopupError('Internal error', title='ERROR')
            return

        header_row = []
        for element in th_elements:
            header_row.append(element.text_content())

        table_data = []
        for i in range(1, len(tr_elements)):
            if len(tr_elements[i]) > 0:
                table_dict = {}
                j = 0
                for t in tr_elements[i].iterchildren():
                    key = th_elements[j].text_content()
                    data = t.text_content().strip()
                    if key == data:
                        break
                    table_dict[key] = data
                    j = j + 1

                if j == len(th_elements):
                    table_data.append(table_dict)

        headers_to_show = self.searchTableHeadingsSizes.keys()
        table_to_show = []
        i = 1
        for table_dict in table_data:
            result_row = []
            for column in headers_to_show:
                if column == '#':
                    result_row.append(str(i))
                    continue
                if not (column in table_dict.keys()):
                    print('\'{}\' is not found in table {}'.format(column, table_dict))
                    sg.PopupError('Internal error: \'{}\' is not found in table'.format(column),
                                  title='ERROR')
                    return None
                result_row.append(table_dict[column])
            table_to_show.append(result_row)
            i += 1

        tableLayout = [[sg.Table(table_to_show,
                                 headings=list(self.searchTableHeadingsSizes.keys()),
                                 justification='left',
                                 auto_size_columns=False,
                                 col_widths=list(self.searchTableHeadingsSizes.values()),
                                 num_rows=10,
                                 key='_db_search_table_')],
                       [sg.Button('OK')]]
        table_window = sg.Window('Select player',
                                 default_button_element_size=(12, 1),
                                 auto_size_buttons=False,
                                 ).Layout(tableLayout)
        button, value = table_window.Read()
        table_window.Close()

        if button == 'OK' and '_db_search_table_' in value:
            if value['_db_search_table_'] is not None and len(value['_db_search_table_']) > 0:
                index = value['_db_search_table_'][0]
                window.FindElement('_db_name_input_').Update(table_to_show[index][self.searchTableIdIndex])

    ## Finds name in chess-db, if search returns uniq name, returns pgn file
    def chessDbFind(self, window: sg.Window, name: str) -> Optional[str]:
        try:
            with self.startOperation('Searching'):
                searchURL = self.config.get('chess-db', 'searchURL').format(name)
                htmlSession = requests.session()
                response = htmlSession.get(url=searchURL)
        except:
            sg.PopupError('Unable to connect chess-db', title='ERROR')
            return None

        ## Not found case
        if self.config.get('chess-db', 'notFoundString') in response.text:
            sg.PopupError('Error: name \'{}\' is not found in database'.format(name), title='ERROR')
            return None

        doc = lh.fromstring(response.text)
        title_elements = doc.xpath('//title')
        if len(title_elements) == 0:
            sg.PopupError('Internal error', title='ERROR')
            return None

        ## not uniquielly found case
        if not (self.config.get('chess-db', 'foundString') in title_elements[0].text_content()):
            self.chessDbShowSearchList(window, doc)
            return None

        # uniq find

        # find href
        href_elements = doc.xpath('//*[@onclick=\'showLoading();\']')
        if len(href_elements) == 0:
            sg.PopupError('Internal error', title='ERROR')
            return None
        href = href_elements[0].attrib['href']

        # find number of games to estimate size
        games_elements = doc.xpath('//a[contains(.,\' games\')]/text()')
        sizeEstimation = None
        if len(games_elements) == 1:
            gamesNumber = int(str(games_elements[0]).strip().split(' ')[0])
            sizeEstimation = PGN_SIZE_PER_GAME * gamesNumber
        return self.chessDbDownloadFile(htmlSession, self.config.get('chess-db', 'base') + href, sizeEstimation)

    ################################################### lichess ########################################################
    ## initializes lichess client
    def initLiChessClient(self) -> None:
        try:
            with open(self.config.get('lichess', 'tokenFile')) as file:
                token = file.read()
        except:
            sg.PopupError('Unable to open lichess token file', title='ERROR')
            return
        session = berserk.TokenSession(token)
        self.lichessClient = berserk.Client(session)

    ## Finds name in liches, if search returns uniq name, returns pgn file
    def lichessDbFind(self, name: str, fromDate: date, tillDate: date) -> Optional[str]:
        try:
            self.lichessClient.users.get_public_data(name)
        except berserk.exceptions.ResponseError as err:
            print(err)
            if err.status_code == 404:
                sg.PopupError('Name \'{}\' is not found'.format(name), title='ERROR')
            else:
                sg.PopupError('Error occurred while connecting to lichess', title='ERROR')
            return None
        start = berserk.utils.to_millis(datetime.datetime.combine(fromDate, datetime.datetime.min.time()))
        end = berserk.utils.to_millis(datetime.datetime.combine(tillDate, datetime.datetime.max.time()))

        games = list(self.lichessClient.games.export_by_player(name, since=start, until=end))
        if len(games) == 0:
            sg.PopupError('No games', title='ERROR')

        filename = sg.PopupGetFile('Save Game', title='Save Game', no_window=True, default_extension='pgn',
                                   save_as=True, file_types=(('PGN Files', '*.pgn'),))
        if filename == '':
            return None

        with self.startOperation('Download games', len(games)) as operation:
            with open(filename, encoding='utf-8', mode='w') as file:
                i = 0
                for game in games:
                    if game['variant'] == 'standard':
                        pgn = self.lichessClient.games.export(game['id'], as_pgn=True)
                        print(pgn, file=file, end='\n\n')
                    operation.update(i + 1)
                    i += 1
        return filename

    ################################################### chess.com ######################################################
    def chesscomDbFind(self, name: str, fromDate: date, tillDate: date) -> Optional[str]:
        htmlSession = requests.session()
        try:
            playerURL = self.config.get('chess.com', 'playerURL').format(name)
            response = htmlSession.get(url=playerURL)
            response_dict = json.loads(response.text)
            errorKey = self.config.get('chess.com', 'errorKey')
            if errorKey in response_dict:
                sg.PopupError('chess.com responded with error: {}'.format(response_dict[errorKey]), title='ERROR')
                return None
        except:
            sg.PopupError('Error in connecting chess.com', title='ERROR')
            return None

        monthsRange = getMonthRange(fromDate, tillDate)
        filename = None
        try:
            responsesList = []
            totalSize = 0

            with self.startOperation('Getting files', len(monthsRange)) as operation:
                i = 0
                for monthDate in monthsRange:
                    monthUrl = self.config.get('chess.com', 'monthURL').format(name, monthDate.year, monthDate.month)
                    response = htmlSession.get(url=monthUrl, stream=True, timeout=10)
                    if 'Content-Length' in response.headers:
                        size = int(response.headers['Content-Length'])
                        responsesList.append(response)
                        totalSize += size
                    operation.update(i)
                    i += 1

            if totalSize == 0:
                sg.PopupError('No Games', title='ERROR')
                return None

            filename = sg.PopupGetFile('Save Game', title='Save Game', no_window=True, default_extension='pgn',
                                       save_as=True, file_types=(('PGN Files', '*.pgn'),))
            if filename == '':
                return None

            dowloadedSize = 0
            sizeFromLastUpdate = 0

            with self.startOperation('Downloading', totalSize) as operation:
                with open(filename, mode='wb') as file:
                    for response in responsesList:
                        for ch in response:
                            file.write(ch)
                            dowloadedSize += len(ch)
                            sizeFromLastUpdate+=len(ch)
                            if sizeFromLastUpdate > 10000:
                                operation.update(dowloadedSize)
                                sizeFromLastUpdate=0
                        file.write(bytes('\n\n', 'utf-8'))
        except:
            sg.PopupError('Error in downloading', title='ERROR')
            try:
                if filename is not None:
                    os.remove(filename)
            except:
                pass
            filename = None

        return filename

    ############################################## UI operations #######################################################

    ## Called after window finalize
    def onWindowFinalize(self, window: sg.Window) -> None:
        today = date.today()

        # There are no normal calendar in pySimpleGUI, so adding it by tkinter
        self.from_calendar = tkcalendar.DateEntry(window.FindElement('_db_from_frame_').Widget,
                                                  width=10,
                                                  year=today.year,
                                                  month=today.month,
                                                  day=today.day,
                                                  date_pattern='dd/mm/Y',
                                                  borderwidth=2)

        self.till_calendar = tkcalendar.DateEntry(window.FindElement('_db_till_frame_').Widget,
                                                  width=10,
                                                  year=today.year,
                                                  month=today.month,
                                                  day=today.day,
                                                  date_pattern='dd/mm/Y',
                                                  borderwidth=2)
        self.from_calendar.pack()
        self.till_calendar.pack()
        self.initLiChessClient()

    ## finds name in choosen database
    def findNameInDatabase(self, window: sg.Window, name: str) -> Optional[DataBaseSearchResult]:
        database = window.FindElement('_db_name_').Get()
        fromdate = self.from_calendar.get_date()
        tilldate = self.till_calendar.get_date()
        if database in self.databaseFindFunctions:
            filename = self.databaseFindFunctions[database](window, name, fromdate, tilldate)
            if filename is not None:
                return DataBaseSearchResult(filename, fromdate, tilldate)
        else:
            sg.PopupError('Database \'{}\' is not supported'.format(database), title='ERROR')
        return None

    ## reacts on window event
    def onEvent(self, window: sg.Window, button) -> Optional[DataBaseSearchResult]:
        if button == '_db_find_':
            return self.findNameInDatabase(window, window.FindElement('_db_name_input_').Get())
        return None
