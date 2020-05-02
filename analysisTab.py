from tkinter import Canvas
from typing import Dict, List, Optional, Union
import PySimpleGUI as sg
import configparser
from datetime import date
import datetime
import tkcalendar
import tkinter
import chess
import chess.engine
import chess.pgn
import os.path
import os
import threading
import copy
import traceback

WHITE = 'White'
BLACK = 'Black'
COLORS = [WHITE, BLACK]

MISTAKE = 'mistake'
UNACCURACY = 'unaccuracy'
NORMAL = 'normal'


## class containes canvas UI info
class CanvasInfo:
    element: object  # canvas element
    x: int  # element center x coordinate
    y: int  # element center y coordinate
    change_fill: bool  # flag denotes if color can be changed when analysing comes to node

    def __init__(self, element: object, x: int, y: int, change_fill: bool):
        self.element = element
        self.x = x
        self.y = y
        self.change_fill = change_fill


## class containes ECO (chess opening) info
class EcoInfo:
    ecoCode: str
    opening: str
    variant: str

    def __init__(self, ecoCode: str, opening: str, variant: str) -> None:
        self.ecoCode = ecoCode
        self.opening = opening
        self.variant = variant

    # Returns short name
    def shortName(self) -> str:
        return '{} ({})'.format(self.opening, self.ecoCode)

    # explanation in form code=opening, variant
    def explanation(self) -> str:
        return '{} = {}, {}'.format(self.ecoCode, self.opening, self.variant)

    # string
    def __str__(self):
        return '{},{},{}'.format(self.ecoCode, self.opening, self.variant)

    # returns hash for dictionary
    def __hash__(self):
        return hash(str(self))


## class combibes eco info and node in game with specific position
class EcoInfoWithNode:
    ecoInfo: EcoInfo
    node: chess.pgn.GameNode

    def __init__(self, ecoInfo: EcoInfo, node: chess.pgn.GameNode) -> None:
        self.ecoInfo = ecoInfo
        self.node = node

    def __hash__(self):
        return hash(self.ecoInfo)


## class for game Node statistics
class GameStats:
    totalGames: int
    white: int
    black: int
    draws: int
    gamesTable: List[List[str]]
    gamesList: List[int]

    def __init__(self, white: int, black: int, draws: int, gamesTable: List[List[str]], gamesList: List[int]) -> None:
        self.totalGames = white + black + draws
        self.white = white
        self.black = black
        self.draws = draws
        self.gamesTable = gamesTable
        self.gamesList = gamesList

    def getLostAndDrawsRatio(self, color: str) -> float:
        if color == WHITE:
            return (self.black + 0.5 * self.draws) / self.totalGames
        else:
            return (self.white + 0.5 * self.draws) / self.totalGames

    def whiteStr(self):
        return '{} ({}%)'.format(self.white, round(self.white * 100 / self.totalGames))

    def blackStr(self):
        return '{} ({}%)'.format(self.black, round(self.black * 100 / self.totalGames))

    def drawStr(self):
        return '{} ({}%)'.format(self.draws, round(self.draws * 100 / self.totalGames))

    def __str__(self):
        return 'white={}, black={}, draws={}, gamesTable={}'.format(self.white, self.black, self.draws, self.gamesTable)

    def __add__(self, other):
        return GameStats(self.white + other.white,
                         self.black + other.black,
                         self.draws + other.draws,
                         self.gamesTable + other.gamesTable,
                         self.gamesList + other.gamesList)

    def __iadd__(self, other):
        self.totalGames = self.totalGames + other.totalGames
        self.white = self.white + other.white
        self.black = self.black + other.black
        self.draws = self.draws + other.draws
        self.gamesTable = self.gamesTable + other.gamesTable
        self.gamesList = self.gamesList + other.gamesList
        assert (self.totalGames == self.white + self.black + self.draws)
        return self


## class for evaluation node statistics
class EvaluationStats:
    score: float
    change: float

    def __init__(self, score: float, change: float) -> None:
        self.score = score
        self.change = change

    def toCommentStr(self) -> str:
        return '&{} &{}'.format(self.score, self.change)

    def scoreStr(self) -> str:
        return '%.2f' % self.score

    def changeStr(self) -> str:
        return '%.2f' % self.change

    @classmethod
    def fromComment(cls, commentStr: str):
        info = commentStr.split('&')
        if len(info) != 3:
            return None
        return cls(float(info[1]), float(info[2]))

    @classmethod
    def fromNode(cls, node: chess.pgn.GameNode):
        return cls.fromComment(node.comment)


## Operation class
class Operation:
    textElement: sg.Text
    progressElement: sg.ProgressBar
    operationName: str
    maxValue: int

    def __init__(self, textElement: sg.Text, progressElement: sg.ProgressBar, operationName: str, maxValue: int):
        self.textElement = textElement
        self.progressElement = progressElement
        self.operationName = operationName
        self.maxValue = maxValue

    def __enter__(self):
        self.textElement.Update('{} (0/{})'.format(self.operationName, self.maxValue))
        self.progressElement.UpdateBar(current_count=0, max=self.maxValue)
        self.progressElement.Update(visible=True)
        return self

    def update(self, count):
        self.textElement.Update('{} ({}/{})'.format(self.operationName, count, self.maxValue))
        self.progressElement.UpdateBar(current_count=count, max=self.maxValue)
        self.progressElement.Update(visible=True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.textElement.Update('')
        self.progressElement.Update(visible=False)


## returns float range list
def getFloatRange(digitsNumber: int, start: float, finish: float, step: float) -> List[str]:
    result: List[str] = []
    x: float = start
    while x < finish:
        result.append('%.{}f'.format(digitsNumber) % x)
        x += step
    return result


## converts x or y  coordinate that must be shown to the xview/yview fraction
def positionToFraction(position: int, maximum: int, screen: int) -> float:
    # try to put element in the center if it is not in the beginning of the screen
    screen_corner = position - screen / 2 if (position > screen / 2) else 0
    return screen_corner / maximum


## Main class
class AnalysisTab:
    analysisCanvas: Canvas
    # Type annotations
    operationsTab: sg.Frame
    analyzeTreeTab: sg.Frame
    analysisResultsTab: sg.Column
    onBoardChange: callable  # function called than board should be updated
    config: configparser.RawConfigParser  # config parser
    clearStages: Dict[str, int]  # on every stage clear operation must clear staff specific to stage
    pgnAllGames: List[chess.pgn.Game]  # all the games in pgn file
    filteredPgnGames: List[chess.pgn.Game]  # games filtered by UI filter
    player: Optional[str]  # player name
    color: Optional[str]  # player's color
    fromDate: Optional[date]  # start date for filtering
    tillDate: Optional[date]  # end date for filtering

    combinedFilename: Optional[str]  # filename of pgn contains combined game and filtered games
    combinedGame: Optional[chess.pgn.Game]  # game combined from all filtered games
    currentNode: Optional[chess.pgn.GameNode]  # node in combined game currently shown in board and analysis tree
    totalNumberOfNodes: Optional[int]  # number of nodes in combined game

    nodeToSanCache: Dict[chess.pgn.GameNode, str]  # cache for san presentation of moves of specific nodes
    elementToNode: Dict[object, chess.pgn.GameNode]  # map from canvas elemnet to combined game node
    nodeToCanvasInfo: Dict[chess.pgn.GameNode, CanvasInfo]  # map from game node to canvas information
    fenToEcoInfo: Dict[str, EcoInfo]  # map from position fen to eco info

    moveClassToFillColor: Dict[str, str]  # map from move classification ('mistake','unaccuracy','normal' to color
    mistakeNodes: List[chess.pgn.GameNode]  # nodes considered to be mistake
    unaccuracyNodes: List[chess.pgn.GameNode]  # nodes considered to be Unaccuracy

    samePositionsNodesMap: Dict[chess.pgn.GameNode, chess.pgn.GameNode]  # first node is actually reference to second
    mistakesTableInfo: List[EcoInfoWithNode]  # list of Eco information and node for current mistakes table
    badGamesTableInfo: List[List[Union[EcoInfoWithNode, List[chess.pgn.GameNode]]]]  # info for current bad games table
    lock: threading.Lock  # lock for various variables that enginge thread uses
    stopThread: bool  # boolean says to engine thread to stop
    thread: Optional[threading.Thread]  # engine thread
    from_calendar: Optional[tkcalendar.DateEntry]  # from calendar widget
    till_calendar: Optional[tkcalendar.DateEntry]  # till calendar widget
    window: Optional[sg.Window]  # Window

    def __init__(self, configFile: str, onBoardChange: callable) -> None:
        self.config = configparser.RawConfigParser()
        self.config.read(configFile)

        self.operationsTab = sg.Frame(title='Operations', layout=[[
            sg.Column([
                [sg.Text('Filename:'),
                 sg.Text('', key='_operations_name_output_', size=(12, 1), background_color='white',
                         text_color='black'),
                 sg.Text('From date:'), sg.Column([[]], key='_operations_from_frame_'),
                 sg.Text('Till date:'), sg.Column([[]], key='_operations_till_frame_'),
                 sg.Text('Color:'),
                 sg.Combo(COLORS, default_value=COLORS[0], key='_operations_color_'),
                 sg.Text('Player:'),
                 sg.Text('', size=(21, 1), key='_operations_player_name_', background_color='white',
                         text_color='black')],
                [sg.Text('Games #:'),
                 sg.Text('', size=(5, 1), key='_operations_games_number_', background_color='white',
                         text_color='black'),
                 sg.Text('Filtered #:'),
                 sg.Text('', size=(5, 1), key='_operations_games_number_filtered', background_color='white',
                         text_color='black'),
                 sg.Text('', size=(30, 1))],
                [sg.Button('Load pgn', key='_operations_load_pgn_', disabled=True),
                 sg.Button('Refresh filter', key='_operations_refresh_filter_', disabled=True),
                 sg.Button('Analyze', key='_operations_analyse_', disabled=True),
                 sg.Button('Show Statistics', key='_operations_statistics_', disabled=True)
                 ],
                [sg.Text('Operation:', size=(8, 1)), sg.Text('', size=(22, 1), key='_operations_operation_name_'),
                 sg.ProgressBar(visible=False, size=(51, 20), key='_operations_progress_bar', max_value=100)],
            ]),
        ]])
        self.analyzeTreeTab = sg.Frame(title='Analysis Tree', layout=[
            [sg.Column([[]], key='_analysis_canvas_frame_')]])

        self.analysisResultsTab = sg.Column([
            [sg.Frame(title='Analisys Statisitcs', layout=[
                [sg.Text('Moves #:', size=(12, 1)),
                 sg.Spin(list(range(1, 30)), initial_value=10, size=(4, 1), key='_analysis_stat_moves_'),
                 sg.Text('Ignored score:', size=(12, 1)),
                 sg.Spin(getFloatRange(1, self.config.getfloat('mistakesTable', 'minimalIgnoredScore'),
                                       self.config.getfloat('mistakesTable', 'maximalIgnoredScore'), 0.1),
                         initial_value=self.config.get('mistakesTable', 'initialIgnoreScore'),
                         size=(4, 1),
                         key='_analysis_stat_ignored_score_')],
                [sg.Text('Minimal change:', size=(12, 1)),
                 sg.Spin(getFloatRange(1, self.config.getfloat('mistakesTable', 'minimalChange'),
                                       self.config.getfloat('mistakesTable', 'maximalChange'), 0.1),
                         initial_value=self.config.get('mistakesTable', 'initialChange'),
                         size=(4, 1),
                         key='_analysis_min_change_'),
                 sg.Text('Sorting criteria:', size=(12, 1)),
                 sg.Combo(['Move #', 'Eval', 'Change'],
                          default_value='Change',
                          size=(7, 1),
                          key='_analysis_stat_sorting_criteria_')],
                [sg.Text('Mistakes table', font=('TkFixedFont', 14), size=(27, 1), justification='center')],
                [sg.Table([[]],
                          headings=['Move #', 'Variant', 'Move', 'Eval', 'Change'],
                          col_widths=[6, 21, 7, 5, 7],
                          auto_size_columns=False,
                          num_rows=5,
                          font=('TkFixedFont', 9),
                          justification='center',
                          key='_analysis_stat_mistakes_table_')],
                [sg.Text('',
                         size=(35, 1),
                         background_color='white',
                         text_color='black',
                         font=('TkFixedFont', 9),
                         key='_analysis_mistake_variant_details_'),
                 sg.Button('Save Games', font=('TkFixedFont', 8), key='analysis_stat_mistakes_save')],
                [sg.Text('Variant moves #:', size=(12, 1)),
                 sg.Spin(list(range(1, 30)), initial_value=10, size=(4, 1), key='_analysis_stat_bad_results_moves_'),
                 sg.Text('Sorting criteria:', size=(12, 1)),
                 sg.Combo(['Games', 'Losts %'], default_value='Games', size=(7, 1),
                          key='_analysis_stat_bad_results_sorting_criteria_')],
                [sg.Text('Variants with bad results', font=('TkFixedFont', 14), size=(27, 1), justification='center')],
                [sg.Table([[]],
                          headings=['Variant', 'Games', 'Wins', 'Losts', 'Draws'],
                          col_widths=[22, 6, 6, 6, 6],
                          auto_size_columns=False,
                          font=('TkFixedFont', 9),
                          num_rows=4,
                          justification='center',
                          key='_analysis_stat_bad_results_table_')],
                [sg.Text('',
                         size=(35, 1),
                         background_color='white',
                         text_color='black',
                         font=('TkFixedFont', 9),
                         key='_analysis_bad_result_variant_details_'),
                 sg.Button('Save Games', font=('TkFixedFont', 8), key='analysis_stat_bad_results_save')]
            ])],
            [sg.Frame(title='Move Info', layout=[
                [sg.Text('Games:', size=(5, 1)),
                 sg.Text('', size=(6, 1), background_color='white', text_color='black', key='_analysis_move_games_')],
                [sg.Text('White:', size=(5, 1)),
                 sg.Text('', size=(6, 1), background_color='white', text_color='black', key='_analysis_move_white_'),
                 sg.Text('Black:', size=(6, 1)),
                 sg.Text('', size=(6, 1), background_color='white', text_color='black', key='_analysis_move_black_'),
                 sg.Text('Draw:', size=(4, 1)),
                 sg.Text('', size=(6, 1), background_color='white', text_color='black', key='_analysis_move_draws_')],
                [sg.Text('Eval:', size=(5, 1)),
                 sg.Text('', size=(6, 1), background_color='white', text_color='black', key='_analysis_move_eval_'),
                 sg.Text('Change:', size=(6, 1)),
                 sg.Text('', size=(6, 1), background_color='white', text_color='black',
                         key='_analysis_move_eval_change_')],
                [sg.Text('Games table', font=('TkFixedFont', 14), size=(26, 1), justification='center')],
                [sg.Table([],
                          auto_size_columns=False,
                          headings=['Date', 'White', 'ELO ', 'Black', 'ELO', 'Result'],
                          col_widths=[9, 10, 5, 10, 5, 7],
                          font=('TkFixedFont', 9),
                          key='_analysis_move_games_table',
                          justification='center',
                          num_rows=5)]
            ])]])

        self.onBoardChange = onBoardChange
        self.clearStages = dict(setFilename=0, loadPgnFile=1, refreshPerod=2, buildCombinedPgn=3, loadCombinedPgn=4,
                                showAnalisysTree=5)
        # pgn filename staff
        self.filename = None
        self.pgnAllGames = []
        self.filteredPgnGames = []
        self.player = None
        self.color = None
        self.fromDate = None
        self.tillDate = None

        # combined pgn staff
        self.combinedFilename = None
        self.combinedGame = None
        self.currentNode = None
        self.totalNumberOfNodes = None

        # caches and maps
        self.nodeToSanCache = {}
        self.elementToNode = {}
        self.nodeToCanvasInfo = {}
        self.fenToEcoInfo = {}
        self.samePositionsNodesMap = {}

        self.moveClassToFillColor = {
            MISTAKE: self.config.get('tree_ui', 'mistakeColor'),
            UNACCURACY: self.config.get('tree_ui', 'unaccuracyColor'),
            NORMAL: self.config.get('tree_ui', 'normalColor')
        }
        self.mistakeNodes = []
        self.unaccuracyNodes = []

        self.mistakesTableInfo = []
        self.badGamesTableInfo = []

        # thread staff
        self.lock = threading.Lock()
        self.stopThread = False
        self.updateTreeLock = threading.Lock()
        self.thread = None
        self.from_calendar = None
        self.till_calendar = None
        self.window = None

    #################################################### Helpers #######################################################
    def getOperationsTab(self) -> sg.Frame:
        return self.operationsTab

    def getAnalyzeTreeTab(self) -> sg.Frame:
        return self.analyzeTreeTab

    def getAnalysisResultsTab(self) -> sg.Column:
        return self.analysisResultsTab

    ## operation start, enables progress bar
    def startOperation(self, operation: str, max_value: int) -> Operation:
        return Operation(self.window.FindElement('_operations_operation_name_'),
                         self.window.FindElement('_operations_progress_bar'),
                         operation,
                         max_value)

    ## clears according to stage
    def clear(self, stage: str) -> None:
        if self.clearStages[stage] <= self.clearStages['setFilename']:
            self.filename = None
            self.window.FindElement('_operations_name_output_').Update('')
            self.window.FindElement('_operations_load_pgn_').Update(disabled=True)

        if self.clearStages[stage] <= self.clearStages['loadPgnFile']:
            self.pgnAllGames.clear()
            self.player = None
            self.window.FindElement('_operations_player_name_').Update('')
            self.window.FindElement('_operations_games_number_').Update('')
            self.window.FindElement('_operations_games_number_filtered').Update('')
            self.window.FindElement('_operations_refresh_filter_').Update(disabled=True)

        if self.clearStages[stage] <= self.clearStages['refreshPerod']:
            self.filteredPgnGames.clear()
            self.color = None
            self.fromDate = None
            self.tillDate = None
            self.window.FindElement('_operations_analyse_').Update(disabled=True)

        if self.clearStages[stage] <= self.clearStages['buildCombinedPgn']:
            self.combinedFilename = None
        if self.clearStages[stage] <= self.clearStages['loadCombinedPgn']:
            self.combinedGame = None
            self.currentNode = None
            self.samePositionsNodesMap.clear()

            self.window.FindElement('_analysis_stat_mistakes_table_').Update([])
            self.window.FindElement('_analysis_stat_bad_results_table_').Update([])
            self.window.FindElement('_analysis_mistake_variant_details_').Update('')
            self.window.FindElement('_analysis_bad_result_variant_details_').Update('')
            self.window.FindElement('_operations_statistics_').Update(disabled=True)
            self.onBoardChange(chess.pgn.Game().board())

        if self.clearStages[stage] <= self.clearStages['showAnalisysTree']:
            self.elementToNode.clear()
            with self.lock:
                self.nodeToCanvasInfo.clear()
                self.analysisCanvas.delete(tkinter.ALL)
            self.window.FindElement('_analysis_move_games_').Update('')
            self.window.FindElement('_analysis_move_white_').Update('')
            self.window.FindElement('_analysis_move_black_').Update('')
            self.window.FindElement('_analysis_move_draws_').Update('')
            self.window.FindElement('_analysis_move_eval_').Update('')
            self.window.FindElement('_analysis_move_eval_change_').Update('')
            self.window.FindElement('_analysis_move_games_table').Update([])

    ## calculates number of nodes for given node
    def calcNodesNumber(self, node: chess.pgn.GameNode) -> int:
        # don't count refernces
        if node.comment == '@':
            return 0

        num = 0
        for variation in node.variations:
            num += self.calcNodesNumber(variation)
        return num + 1

    # builds nodes list with BFS
    def buildBFSNodesList(self) -> List[chess.pgn.GameNode]:
        with self.startOperation('Building list to analyaze', self.totalNumberOfNodes) as operation:
            i = 0
            resultList = []
            workingList = [self.combinedGame]
            while len(workingList) != 0:
                node = workingList.pop(0)
                operation.update(i)
                resultList.append(node)
                for variation in node.variations:
                    if variation.comment != '@':
                        workingList.append(variation)
                i += 1
            assert (len(resultList) == self.totalNumberOfNodes)
        return resultList

    # returns move clasification (mistake,unaccuracy, normal)
    def classifyMove(self, scoreChange: float, color: str) -> str:
        mistakeMoveChange: float = self.config.getfloat('moves_classification', 'mistakeMoveChange')
        unaccuracyMoveChange: float = self.config.getfloat('moves_classification', 'unaccuracyMoveChange')
        if (scoreChange < -mistakeMoveChange and color == chess.WHITE) or \
                (scoreChange > mistakeMoveChange and color == chess.BLACK):
            return MISTAKE
        else:
            if (scoreChange < -unaccuracyMoveChange and color == chess.WHITE) or \
                    (scoreChange > unaccuracyMoveChange and color == chess.BLACK):
                return UNACCURACY
            else:
                return NORMAL

    # loads ECO book
    def loadEcoBook(self) -> None:
        try:
            # count number of games
            pgn = open(self.config.get('eco', 'ecoBook'))
            games_count = 0
            for line in pgn:
                games_count += line.count('Site')
            pgn.seek(0)

            with self.startOperation('Download Eco Book', games_count) as operation:
                i = 0
                while True:
                    game = chess.pgn.read_game(pgn)
                    if game is not None:
                        eco = game.headers['Site']
                        opening = game.headers[WHITE]
                        opening_variation = game.headers[BLACK]
                        if opening_variation == '?':
                            opening_variation = 'None'

                        node = game
                        while len(node.variations) != 0:
                            node = node.variations[0]
                        self.fenToEcoInfo[node.board().fen().split('-')[0]] = EcoInfo(eco, opening, opening_variation)
                        i += 1
                        operation.update(i)
                    else:
                        break
        except:
            sg.PopupError('Unable to load eco book', 'ERROR')

    # Returns node games info
    def getNodeGameStats(self, node) -> GameStats:
        if node.comment == '@':
            return self.getNodeGameStats(self.samePositionsNodesMap[node])

        gameNumbers = node.comment.split(',')
        gameNumbers.pop(-1).split('&')
        white = black = draw = 0
        table_to_show = []
        gamesList: List[int] = []
        for numberStr in gameNumbers:
            i = int(numberStr)
            gamesList.append(i)
            gameDate = datetime.datetime.strptime(self.filteredPgnGames[i].headers['Date'], '%Y.%m.%d').date()

            whiteFullName = self.filteredPgnGames[i].headers[WHITE].replace(' ', '').split(',')
            whiteElo = self.filteredPgnGames[i].headers['WhiteElo']
            if len(whiteFullName) > 1:
                whiteName = '{} {}.'.format(whiteFullName[0], whiteFullName[1][0])
            else:
                whiteName = whiteFullName[0]

            blackFullName = self.filteredPgnGames[i].headers[BLACK].replace(' ', '').split(',')
            blackElo = self.filteredPgnGames[i].headers['BlackElo']
            if len(blackFullName) > 1:
                blackName = '{} {}.'.format(blackFullName[0], blackFullName[1][0])
            else:
                blackName = blackFullName[0]

            result = self.filteredPgnGames[i].headers['Result'].replace(' ', '')
            table_to_show.append([gameDate.strftime('%d/%m/%y'), whiteName, whiteElo, blackName, blackElo, result])
            if result == '1-0':
                white += 1
            if result == '0-1':
                black += 1
            if result == '1/2-1/2':
                draw += 1

        assert (white + black + draw == len(gameNumbers))
        return GameStats(white, black, draw, table_to_show, gamesList)

    # returns most close eco entry in book
    def getNodeEcoEntry(self, node: chess.pgn.GameNode) -> Optional[EcoInfoWithNode]:
        board = node.board()
        result_node = node
        while True:
            fen = board.fen().split('-')[0]
            if fen in self.fenToEcoInfo:
                return EcoInfoWithNode(self.fenToEcoInfo[fen], result_node)
            try:
                board.pop()
                result_node = result_node.parent
            except:
                return None

    # Evaluates nodes that are lower than given depth (half_moves, odd-is white, even - black) from start game
    def scanNodesToDepth(self, node: chess.pgn.GameNode, half_moves: int, remaining_half_moves: int,
                         evaluateNode: callable, ignoreReferences: bool = False) -> None:
        if (ignoreReferences is False) and (node.comment == '@'):
            node = self.samePositionsNodesMap[node]
        evaluateNode(node, half_moves)
        if remaining_half_moves == 0:
            return
        for variation in node.variations:
            self.scanNodesToDepth(variation, half_moves + 1, remaining_half_moves - 1, evaluateNode, ignoreReferences)

    ## adds node and all its descedents to the combined game node
    def addNode(self, combinedNode: chess.pgn.GameNode, node: chess.pgn.GameNode, gameNumber: int, board: chess.Board,
                infenCache: Dict[str, chess.pgn.GameNode], outFenCache: Dict[str, chess.pgn.GameNode],
                addGamesNumbersComments: bool = True, endGameComment: Optional[str] = None) -> None:

        if node.move is not None:
            board.push(node.move)
            fen: str = board.fen().split('-')[0]
            if fen in infenCache:
                if combinedNode != infenCache[fen]:
                    # we found same position put current combined node as a reference
                    self.samePositionsNodesMap[combinedNode] = infenCache[fen]
                    combinedNode.comment = '@'
                    combinedNode = infenCache[fen]
            else:
                # if it is not in inFen cache put it to the out fen cache
                outFenCache[fen] = combinedNode

        for variation in node.variations:
            if combinedNode.has_variation(variation.move):
                new_node = combinedNode.variation(variation.move)
            else:
                new_node = combinedNode.add_variation(variation.move)
            if addGamesNumbersComments:
                new_node.comment += str(gameNumber) + ','
            self.addNode(new_node, variation, gameNumber, board, infenCache, outFenCache, addGamesNumbersComments,
                         endGameComment)
        if len(node.variations) == 0 and endGameComment is not None:
            combinedNode.comment += endGameComment
        if node.move is not None:
            board.pop()

    # annotates mistakes or errors in output pgn
    def annotateOutGame(self, gameNumber: int, fenCache: Dict[str, chess.pgn.GameNode],
                        nodesList: List[chess.pgn.GameNode], annotationStr: str):
        for node in nodesList:
            if gameNumber in self.getNodeGameStats(node).gamesList:
                evalStats = EvaluationStats.fromNode(node)
                if evalStats is not None:
                    fen = node.board().fen().split('-')[0]
                    assert (fen in fenCache)
                    out_mistake_node = fenCache[fen]
                    if out_mistake_node.comment == '':
                        out_mistake_node.comment = '{}, score={} change={}'.format(annotationStr, evalStats.scoreStr(),
                                                                                   evalStats.changeStr())

    # saves annotated output pgn
    def buildOutPgn(self, nodes: List[chess.pgn.GameNode], out_filename):
        result_game = chess.pgn.Game()
        for node in nodes:
            gamesStats = self.getNodeGameStats(node)
            gamesList = gamesStats.gamesList
            gameTable = gamesStats.gamesTable
            j = 0
            for gameNumber in gamesList:
                outFenCache: Dict[str, chess.pgn.GameNode] = {}
                endGameComment = '{} ({}) - {} ({}), {}, {}'.format(gameTable[j][1], gameTable[j][2], gameTable[j][3],
                                                                    gameTable[j][4], gameTable[j][5], gameTable[j][0])
                self.addNode(result_game, self.filteredPgnGames[gameNumber], gameNumber, result_game.board(), {},
                             outFenCache, False,
                             endGameComment)

                # Annotate
                with self.lock:
                    mistakeNodes = copy.copy(self.mistakeNodes)
                    unaccuracyNodes = copy.copy(self.unaccuracyNodes)
                self.annotateOutGame(gameNumber, outFenCache, mistakeNodes, MISTAKE)
                self.annotateOutGame(gameNumber, outFenCache, unaccuracyNodes, UNACCURACY)
                j += 1

        with open(out_filename, encoding='utf-8', mode='w') as file:
            print(result_game, file=file, end='\n\n')

    ############################################## Combined pgn buildig ################################################
    @staticmethod
    def checkNodeForReferenceBuilding(node: chess.pgn.GameNode, fenCache: Dict[str, chess.pgn.GameNode],
                                      referencesList: List[chess.pgn.GameNode], operation: Operation) -> None:

        operation.update(len(fenCache.keys()))
        if node.comment == '@':
            referencesList.append(node)
            return
        fenCache[node.board().fen().split('-')[0]] = node

    def buildReferences(self) -> None:
        with self.startOperation('Build references', self.totalNumberOfNodes) as operation:
            fenCache: Dict[str, chess.pgn.GameNode] = {}
            referncesList: List[chess.pgn.GameNode] = []
            self.scanNodesToDepth(self.combinedGame, 0, 10000,
                                  lambda x, y: self.checkNodeForReferenceBuilding(x, fenCache, referncesList,
                                                                                  operation),
                                  True)
            for node in referncesList:
                fen = node.board().fen().split('-')[0]
                assert (fen in fenCache)
                self.samePositionsNodesMap[node] = fenCache[fen]

    ## Loads combined pgn
    def loadCombinedPgn(self) -> bool:
        self.clear('loadCombinedPgn')
        if self.combinedFilename is None:
            return False

        try:
            with self.startOperation('Load combined pgn', 200) as operation:
                with open(self.combinedFilename, encoding='utf-8') as pgn:
                    # load first game it is actually half of entire pgn
                    self.combinedGame = chess.pgn.read_game(pgn)
                    if self.combinedGame is None:
                        print('No combined game')
                        raise Exception('No combined game')
                    operation.update(100)
                    self.player = self.combinedGame.headers[self.color]
                    self.currentNode = self.combinedGame

                    gamesNumber = int(self.combinedGame.comment.split('&')[0])
                    self.totalNumberOfNodes = self.calcNodesNumber(self.combinedGame)
                    gamesList = []
                    i = 0
                    while True:
                        game: Optional[chess.pgn.Game] = chess.pgn.read_game(pgn)
                        if game is not None:
                            gamesList.append(game)
                            i = i + 1
                            if i > gamesNumber:
                                print('Number of pgns in file is not correct', i, gamesNumber)
                                raise Exception('Number of pgns in file is not correct')
                            operation.update(100 + int(i * 100 / gamesNumber))
                        else:
                            break
                    if i != gamesNumber:
                        raise Exception('Number of pgns in file is not correct')
                    self.filteredPgnGames = gamesList
                    self.window.FindElement('_operations_games_number_filtered').Update(len(self.filteredPgnGames))

                    self.buildReferences()
                    return True

        except:
            os.remove(self.combinedFilename)
            self.clear('loadCombinedPgn')
            return False

    # sorts combined pgn according number of games in each node
    def sortCombinedPgn(self, node: chess.pgn.GameNode, number_evaluated: int, update_function: callable) -> int:
        gameNumbers: List[List[(chess.pgn.GameNode, int)]] = []

        variation: chess.pgn.GameNode
        for variation in node.variations:
            gameNumbers.append([variation, len(variation.comment.split(','))])
        gameNumbers.sort(key=lambda x: x[1], reverse=True)
        i: int
        for i in range(len(gameNumbers)):
            j: int = 0
            while node.variations[j] != gameNumbers[i][0]:
                j += 1
            assert (j >= i)
            k: int
            for k in range(j - i):
                node.promote(gameNumbers[i][0].move)
            i += 1
        n: int = number_evaluated
        # run recursion
        for variation in node.variations:
            n = self.sortCombinedPgn(variation, n, update_function)
        update_function(n + 1)
        return n + 1

    ## saves combine pgn
    def saveCombinedPgn(self) -> bool:
        try:
            with self.startOperation('Save combined pgn', 2 * len(self.filteredPgnGames)) as operation:
                with open(self.combinedFilename, encoding='utf-8', mode='w') as file:
                    i: int = 0
                    print(self.combinedGame, file=file, end="\n\n")
                    i += len(self.filteredPgnGames)
                    operation.update(i)
                    game: chess.pgn.GameNode
                    for game in self.filteredPgnGames:
                        print(game, file=file, end="\n\n")
                        operation.update(i)
                        i += 1
                return True
        except:
            sg.PopupError('Unable to save game to ', title='ERROR')
            try:
                os.remove(self.combinedFilename)
            except:
                pass
            return False

    ## Builds combined pgn from all games
    def buildCombinedPgn(self) -> bool:
        self.clear('buildCombinedPgn')
        self.combinedFilename = '{}_{}_{}_{}.pgn'.format(self.filename.split('.')[0],
                                                         self.fromDate.strftime('%Y_%m_%d'),
                                                         self.tillDate.strftime('%Y_%m_%d'),
                                                         self.color)
        if os.path.exists(self.combinedFilename):
            if self.loadCombinedPgn():
                return True

        # build
        with self.startOperation('Build combined pgn', len(self.filteredPgnGames)) as operation:
            self.combinedGame = chess.pgn.Game()
            self.currentNode = self.combinedGame
            self.combinedGame.comment = str(len(self.filteredPgnGames))
            self.combinedGame.headers[self.color] = self.player
            i: int = 0

            fenCache: Dict[str, chess.pgn.GameNode] = {}
            for game in self.filteredPgnGames:
                tmpFenCache: Dict[str, chess.pgn.GameNode] = {}
                self.addNode(self.combinedGame, game, i, game.board(), fenCache, tmpFenCache)
                fenCache.update(tmpFenCache)
                i += 1
                operation.update(i)
            self.totalNumberOfNodes = self.calcNodesNumber(self.combinedGame)

        with self.startOperation('Sort combined pgn', self.totalNumberOfNodes) as operation:
            self.sortCombinedPgn(self.combinedGame,
                                 0,
                                 operation.update)

        # save
        if not (self.saveCombinedPgn()):
            self.clear('buildCombinedPgn')
            return False
        return True

    ############################################# Canvas sub-operations ###############################################
    # return san (from cache of from board
    def getSan(self, node: chess.pgn.GameNode, board: chess.Board) -> str:
        if node in self.nodeToSanCache:
            return self.nodeToSanCache[node]
        san: str = board.san(node.move)
        self.nodeToSanCache[node] = san
        return san

    ## shows move in canvas widget
    def addMoveToCanvas(self, node: chess.pgn.GameNode, coordx: int, coordy: int, move_text: str, parentx: int,
                        parenty: int, fill: str, change_fill: bool) -> None:
        element = self.analysisCanvas.create_rectangle(coordx - self.config.getint('tree_ui', 'moveX'),
                                                       coordy - self.config.getint('tree_ui', 'moveY'),
                                                       coordx + self.config.getint('tree_ui', 'moveX'),
                                                       coordy + self.config.getint('tree_ui', 'moveY'),
                                                       fill=fill)
        self.elementToNode[element] = node
        with self.lock:
            self.nodeToCanvasInfo[node] = CanvasInfo(element, coordx, coordy, change_fill)

        element = self.analysisCanvas.create_text(coordx, coordy, text=move_text, font=("TkFixedFont", 8))
        self.elementToNode[element] = node

        if parentx is not None:
            if parenty == coordy:
                self.analysisCanvas.create_line(parentx + self.config.getint('tree_ui', 'moveX'),
                                                parenty,
                                                coordx - self.config.getint('tree_ui', 'moveX'),
                                                coordy,
                                                arrow=tkinter.LAST)
            else:
                self.analysisCanvas.create_line(parentx,
                                                parenty + self.config.getint('tree_ui', 'moveY'),
                                                parentx,
                                                coordy)
                self.analysisCanvas.create_line(parentx,
                                                coordy,
                                                coordx - self.config.getint('tree_ui', 'moveX'),
                                                coordy,
                                                arrow=tkinter.LAST)

    ## finishes variation in Canvas if needed
    def finishVariationCanvaseIfNeeded(self, node: chess.pgn.GameNode, current_node: chess.pgn.GameNode) -> bool:
        # in case it is last move in variation - it is not needed
        if len(node.variations) == 0:
            return False

        if node == current_node:
            return False

        # Try to find current.node in previous moves of node
        tmpNode = node
        distance = 0

        while tmpNode is not None and tmpNode != current_node:
            tmpNode = tmpNode.parent
            distance += 1

        # If found  - finish or not according to distance
        finish_variation = (tmpNode is not None) and (distance > self.config.getint('tree_ui', 'showMovesFromCurrent'))

        # Try to find node in previous moves of current_node if we did not find in opposite direction
        if tmpNode is None:
            tmpNode = current_node
            while tmpNode is not None and tmpNode != node:
                tmpNode = tmpNode.parent
            # not found it is side variation - finish it
            finish_variation = (tmpNode is None)

        # Finally finish if needed
        return finish_variation

    ## shows game starting from current node in canvas
    def showGameInCanvas(self, node: chess.pgn.GameNode, current_node: chess.pgn.GameNode, coordx: int, coordy: int,
                         half_move: int, board: chess.Board) -> int:
        if node.move is not None:
            board.push(node.move)
            parentx = coordx
            parenty = coordy
        else:
            parentx = None
            parenty = None

        finishVariation = self.finishVariationCanvaseIfNeeded(node, current_node)

        # First
        y = coordy
        i = 0
        for variation in node.variations:
            x = coordx + self.config.getint('tree_ui', 'moveDistanceX')
            if i != 0:
                y += self.config.getint('tree_ui', 'moveDistanceY')
            if half_move % 2 == 0:
                move_text = '{}.{}'.format(str(int(half_move / 2) + 1), self.getSan(variation, board))
            else:
                move_text = self.getSan(variation, board)
            # in case where are more than one variation new line and move tab space
            fill = self.config.get('tree_ui', 'unanalizedColor')
            if variation == current_node:
                fill = self.config.get('tree_ui', 'currentMoveColor')
            else:
                if variation.comment == '@':
                    fill = self.config.get('tree_ui', 'referenceColor')
                else:
                    evalStats: EvaluationStats = EvaluationStats.fromNode(variation)
                    if evalStats is not None:
                        fill = self.moveClassToFillColor[self.classifyMove(evalStats.change, board.turn)]

            if finishVariation and variation.comment != '@':
                self.addMoveToCanvas(variation, x, y, '...', parentx, parenty,
                                     self.config.get('tree_ui', 'unanalizedColor'), False)
            else:
                self.addMoveToCanvas(variation, x, y, move_text, parentx, parenty, fill, True)
                y = self.showGameInCanvas(variation, current_node, x, y, half_move + 1, board)

            i += 1

        if node.move is not None:
            board.pop()
        return y

    ## shows analysis tree
    def showAnalisysTree(self) -> None:
        self.clear('showAnalisysTree')
        self.showGameInCanvas(self.combinedGame, self.currentNode, -self.config.getint('tree_ui', 'moveX'),
                              self.config.getint('tree_ui', 'moveDistanceY'), 0,
                              self.combinedGame.board())
        bbox = self.analysisCanvas.bbox(tkinter.ALL)
        maxx = bbox[2]
        maxy = bbox[3]
        self.analysisCanvas.config(scrollregion=(0, 0, maxx, maxy))
        if self.currentNode in self.nodeToCanvasInfo:
            canvasInfo = self.nodeToCanvasInfo[self.currentNode]
            self.analysisCanvas.xview_moveto(
                positionToFraction(canvasInfo.x, maxx, self.config.getint('tree_ui', 'canvasSizeX')))
            self.analysisCanvas.yview_moveto(
                positionToFraction(canvasInfo.y, maxy, self.config.getint('tree_ui', 'canvasSizeY')))

    ############################################## Updating Mistakes table #############################################
    ## checks specific node, uppends it to the list if it is a mistake
    def checkNodeToBeMistake(self, node: chess.pgn.GameNode, half_move: int, ignoreScore: float, changeScore: float,
                             nodesDict: Dict[chess.pgn.GameNode, int]) -> None:
        # check that it is move of correct color
        if (self.color == WHITE) and (half_move % 2 == 0):
            return
        if (self.color == BLACK) and (half_move % 2 == 1):
            return
        if node in nodesDict:
            return

        evalStats = EvaluationStats.fromNode(node)

        # if not analysed already
        if evalStats is None:
            return

        # change score
        if self.color == WHITE and evalStats.change > -changeScore:
            return
        if self.color == BLACK and evalStats.change < changeScore:
            return

        # ignore score
        parentEval = evalStats.score - evalStats.change
        if abs(evalStats.score) > ignoreScore and abs(parentEval) > ignoreScore:
            return

        nodesDict[node] = half_move

    ## Updates mistakes table
    def updateMistakesTable(self, values) -> None:
        stat_moves: int = int(values['_analysis_stat_moves_'])
        ignore_score: float = float(values['_analysis_stat_ignored_score_'])
        min_change: float = float(values['_analysis_min_change_'])
        if self.color == WHITE:
            sorting_to_lambda: Dict[str, callable] = {'Move #': lambda x: x[0],
                                                      'Eval': lambda x: -float(x[3]),
                                                      'Change': lambda x: float(x[4])
                                                      }
        else:
            sorting_to_lambda: Dict[str, callable] = {'Move #': lambda x: x[0],
                                                      'Eval': lambda x: float(x[3]),
                                                      'Change': lambda x: -float(x[4])
                                                      }

        sorting_lambda: callable = sorting_to_lambda[values['_analysis_stat_sorting_criteria_']]

        if self.color == WHITE:
            half_moves = stat_moves * 2 - 1
        else:
            half_moves = stat_moves
        nodesDict: Dict[chess.pgn.GameNode, int] = {}

        self.scanNodesToDepth(self.combinedGame,
                              0,
                              half_moves,
                              lambda x, half_move: self.checkNodeToBeMistake(x,
                                                                             half_move,
                                                                             ignore_score,
                                                                             min_change,
                                                                             nodesDict))
        self.mistakesTableInfo.clear()
        mistakes_table: List[List[(int, str, EcoInfoWithNode)]] = []
        for node in nodesDict:
            evalStats: EvaluationStats = EvaluationStats.fromNode(node)
            assert (evalStats is not None)
            eco_info_node: EcoInfoWithNode = self.getNodeEcoEntry(node)
            # here we need original node and not eco node
            eco_info_node.node = node
            entry = [int((nodesDict[node] + 1) / 2),
                     eco_info_node.ecoInfo.shortName() if eco_info_node is not None else 'None',
                     node.san(),
                     evalStats.scoreStr(),
                     evalStats.changeStr(),
                     eco_info_node]
            mistakes_table.append(entry)

        mistakes_table.sort(key=sorting_lambda)
        for entry in mistakes_table:
            eco_info_node = entry.pop(-1)
            self.mistakesTableInfo.append(eco_info_node)

        self.window.FindElement('_analysis_stat_mistakes_table_').Update(mistakes_table)

    ########################################### Updating Bad results table #############################################
    ## checks specific node, uppends it to the list if it can be in bad_results list
    @staticmethod
    def checkNodeToBeInBadResultTable(node, half_move, max_half_move, nodesList):
        if half_move == max_half_move and (node not in nodesList):
            nodesList.append(node)

    ## updates bad results table
    def updateBadResultsTable(self, values) -> None:
        moves: int = values['_analysis_stat_bad_results_moves_']
        sorting_to_lambda: Dict[str, callable] = {'Games': lambda x: -x[1],
                                                  'Losts %': lambda x: -float(x[3] / x[1]),
                                                  }
        sorting_lambda = sorting_to_lambda[values['_analysis_stat_bad_results_sorting_criteria_']]
        if self.color == WHITE:
            half_moves: int = moves * 2 - 1
        else:
            half_moves: int = moves
        nodes_list: List[chess.pgn.GameNode] = []
        # Get all nodes
        self.scanNodesToDepth(self.combinedGame,
                              0,
                              half_moves,
                              lambda x, half_move: self.checkNodeToBeInBadResultTable(x,
                                                                                      half_move,
                                                                                      half_moves,
                                                                                      nodes_list))
        # unify all nodes with same eco
        ecoInfoToGamesStats: Dict[EcoInfo, List[Union[GameStats, EcoInfoWithNode, List[chess.pgn.GameNode]]]] = {}
        for node in nodes_list:
            ecoInfoWithNode: EcoInfoWithNode = self.getNodeEcoEntry(node)
            if ecoInfoWithNode.ecoInfo not in ecoInfoToGamesStats:
                ecoInfoToGamesStats[ecoInfoWithNode.ecoInfo] = [self.getNodeGameStats(node), ecoInfoWithNode, [node]]
            else:
                ecoInfoToGamesStats[ecoInfoWithNode.ecoInfo][0] += self.getNodeGameStats(node)
                ecoInfoToGamesStats[ecoInfoWithNode.ecoInfo][2].append(node)

        badGamesTable = []
        self.badGamesTableInfo.clear()
        minLostRatio = self.config.getfloat('badResultsTable', 'minLostRatio')

        # now fill the table
        for ecoInfo in ecoInfoToGamesStats:
            gamesStats: GameStats = ecoInfoToGamesStats[ecoInfo][0]

            if self.color == WHITE:
                wins: int = gamesStats.white
                losts: int = gamesStats.black
            else:
                wins: int = gamesStats.black
                losts: int = gamesStats.white

            if gamesStats.getLostAndDrawsRatio(self.color) > minLostRatio:
                badGamesTable.append([ecoInfo.shortName(),
                                      gamesStats.totalGames,
                                      wins,
                                      losts,
                                      gamesStats.draws,
                                      ecoInfoToGamesStats[ecoInfo][1],
                                      ecoInfoToGamesStats[ecoInfo][2]])
        badGamesTable.sort(key=sorting_lambda)
        for entry in badGamesTable:
            entry_list: List[chess.pgn.GameNode] = entry.pop(-1)
            entryEcoInfoWithNode: EcoInfoWithNode = entry.pop(-1)
            self.badGamesTableInfo.append([entryEcoInfoWithNode, entry_list])
        self.window.FindElement('_analysis_stat_bad_results_table_').Update(badGamesTable)

    ############################################## UI operations #######################################################
    def onWindowFinalize(self, window: sg.Window) -> None:
        print('AnalysisTab::onWindowFinalize')
        today = date.today()

        # There are no normal calendar in pySimpleGUI, so adding it by tkinter
        self.from_calendar = tkcalendar.DateEntry(window.FindElement('_operations_from_frame_').Widget,
                                                  width=10,
                                                  year=today.year,
                                                  month=today.month,
                                                  day=today.day,
                                                  date_pattern='dd/mm/Y',
                                                  borderwidth=2)

        self.till_calendar = tkcalendar.DateEntry(window.FindElement('_operations_till_frame_').Widget,
                                                  width=10,
                                                  year=today.year,
                                                  month=today.month,
                                                  day=today.day,
                                                  date_pattern='dd/mm/Y',
                                                  borderwidth=2)
        self.from_calendar.pack()
        self.till_calendar.pack()

        frame1 = tkinter.Frame(window.FindElement('_analysis_canvas_frame_').Widget)
        frame1.pack()
        xscrollbar = tkinter.Scrollbar(frame1, orient=tkinter.HORIZONTAL)
        xscrollbar.grid(row=1, column=0, sticky=tkinter.N + tkinter.S + tkinter.E + tkinter.W)
        yscrollbar = tkinter.Scrollbar(frame1)
        yscrollbar.grid(row=0, column=1, sticky=tkinter.N + tkinter.S + tkinter.E + tkinter.W)
        self.analysisCanvas = tkinter.Canvas(frame1,
                                             width=self.config.getint('tree_ui', 'canvasSizeX'),
                                             height=self.config.getint('tree_ui', 'canvasSizeY'),
                                             bg='white')
        self.analysisCanvas.grid(row=0, column=0)
        xscrollbar.config(command=self.analysisCanvas.xview)
        yscrollbar.config(command=self.analysisCanvas.yview)
        self.analysisCanvas.bind('<Button-1>', self.onCanvasClick)
        self.window = window
        window.FindElement('_analysis_stat_mistakes_table_').bind('<ButtonRelease-1>', 'click_')
        window.FindElement('_analysis_stat_bad_results_table_').bind('<ButtonRelease-1>', 'click_')
        self.loadEcoBook()

    ## sets filename
    def setFilename(self, filename: str) -> None:
        self.exitThread()
        self.clear('setFilename')
        self.filename = filename
        split_filename = filename.split('/')
        self.window.FindElement('_operations_name_output_').Update(split_filename[len(split_filename) - 1])
        self.window.FindElement('_operations_load_pgn_').Update(disabled=False)

    ## sets combined filename
    def setCombinedFilename(self, filename: str, values) -> None:
        self.exitThread()
        self.clear('setFilename')
        # build short filename and path
        splitted_filename = filename.split('/')
        short_filename = splitted_filename.pop(-1)
        path = ''
        for part in splitted_filename:
            path += part + '/'

        # check that filename format is correct
        splitted_filename = short_filename.split('_')
        while len(splitted_filename) > 8:
            splitted_filename[0] += '_' + splitted_filename.pop(1)

        try:
            self.filename = '{}{}.pgn'.format(path, splitted_filename[0])
            fromDate = date(int(splitted_filename[1]), int(splitted_filename[2]), int(splitted_filename[3]))
            tillDate = date(int(splitted_filename[4]), int(splitted_filename[5]), int(splitted_filename[6]))
            color = splitted_filename[7].split('.')[0]
            if not (color in COLORS):
                raise Exception('')
        except:
            sg.PopupError('Name format of {} is not correct'.format(short_filename))
            self.clear('setFilename')
            return

        ## Load original pgn
        if not (self.loadPgnFile(values)):
            self.clear('setFilename')
            return
        ## load combined pgn
        self.combinedFilename = filename
        self.fromDate = fromDate
        self.tillDate = tillDate
        self.color = color
        if not (self.loadCombinedPgn()):
            sg.PopupError('Unable to load from {}'.format(short_filename))
            self.clear('setFilename')
            return

        # Update UI
        self.window.FindElement('_operations_name_output_').Update(self.filename.split('/').pop(-1))
        self.from_calendar.set_date(self.fromDate)
        self.till_calendar.set_date(self.tillDate)
        self.window.FindElement('_operations_player_name_').Update(self.player)
        self.window.FindElement('_operations_games_number_').Update(len(self.filteredPgnGames))
        self.window.FindElement('_operations_games_number_filtered').Update(len(self.filteredPgnGames))
        index = 0
        while COLORS[index] != self.color:
            index += 1
        self.window.FindElement('_operations_color_').Update(set_to_index=index)
        self.window.FindElement('_operations_load_pgn_').Update(disabled=False)
        self.window.FindElement('_operations_refresh_filter_').Update(disabled=False)
        if len(self.filteredPgnGames) > 0:
            self.window.FindElement('_operations_analyse_').Update(disabled=False)

    ## sets dates
    def setDates(self, fromDate, tillDate):
        self.from_calendar.set_date(fromDate)
        self.till_calendar.set_date(tillDate)

    ## refreshes current period
    def refreshFilter(self, values) -> None:
        self.exitThread()
        self.clear('refreshPerod')
        self.fromDate = self.from_calendar.get_date()
        self.tillDate = self.till_calendar.get_date()
        self.color = values['_operations_color_']
        for game in self.pgnAllGames:
            datestring = game.headers['Date']
            if datestring.find('?') == -1:
                gameDate = datetime.datetime.strptime(datestring, '%Y.%m.%d').date()
                if self.fromDate <= gameDate <= self.tillDate and game.headers[self.color] == self.player:
                    self.filteredPgnGames.append(game)
        self.window.FindElement('_operations_games_number_filtered').Update(len(self.filteredPgnGames))
        if len(self.filteredPgnGames) > 0:
            self.window.FindElement('_operations_analyse_').Update(disabled=False)

    ## loads pgn
    def loadPgnFile(self, values) -> bool:
        self.exitThread()
        if self.filename is None:
            sg.PopupError('File is not set', title='ERROR')
            return False

        try:
            self.clear('loadPgnFile')
            pgn = open(self.filename, encoding='utf-8')
            games_count = 0
            for line in pgn:
                games_count += line.count(COLORS[0])

            playersDictionary = {}
            pgn.seek(0)
            gamesToShow = 0
            with self.startOperation('Loading Pgn', games_count) as operation:
                while True:
                    game = chess.pgn.read_game(pgn)
                    if game is not None:
                        addGame = game.headers[COLORS[0]] != '?'
                        if 'Variant' in game.headers:
                            if game.headers['Variant'] != '?' and game.headers['Variant'] != 'Standard':
                                addGame = False
                        if addGame:
                            self.pgnAllGames.append(game)
                            for color in COLORS:
                                if not (game.headers[color] in playersDictionary):
                                    playersDictionary[game.headers[color]] = 0
                                playersDictionary[game.headers[color]] += 1
                        operation.update(gamesToShow)
                        gamesToShow += 1
                    else:
                        break

                if len(self.pgnAllGames) == 0:
                    sg.PopupError('No games', title='ERROR')
                    return False

                self.player = max(playersDictionary.keys(), key=(lambda k: playersDictionary[k]))
                self.window.FindElement('_operations_player_name_').Update(self.player)
                self.window.FindElement('_operations_games_number_').Update(len(self.pgnAllGames))
                self.window.FindElement('_operations_refresh_filter_').Update(disabled=False)
                self.refreshFilter(values)
                return True

        except:
            traceback.print_exc()
            sg.PopupError('Error in loading pgn', title='ERROR')
            return False

    # shows node(move) info
    def showNodeInfo(self, node: chess.pgn.GameNode) -> None:
        assert (node.comment != '@')
        gamesStats: GameStats = self.getNodeGameStats(node)
        self.window.FindElement('_analysis_move_games_').Update(gamesStats.totalGames)
        self.window.FindElement('_analysis_move_white_').Update(gamesStats.whiteStr())
        self.window.FindElement('_analysis_move_black_').Update(gamesStats.blackStr())
        self.window.FindElement('_analysis_move_draws_').Update(gamesStats.drawStr())
        self.window.FindElement('_analysis_move_games_table').Update(gamesStats.gamesTable)

        evalStats: Optional[EvaluationStats] = EvaluationStats.fromNode(node)
        if evalStats is not None:
            self.window.FindElement('_analysis_move_eval_').Update(evalStats.scoreStr())
            self.window.FindElement('_analysis_move_eval_change_').Update(evalStats.changeStr())

    # sets current node, than refreshes tree, board and another staff
    def setCurrentNode(self, currentNode: chess.pgn.GameNode) -> None:
        if currentNode.comment == '@':
            self.currentNode = self.samePositionsNodesMap[currentNode]
        else:
            self.currentNode = currentNode

        self.showAnalisysTree()
        self.onBoardChange(self.currentNode.board())
        self.showNodeInfo(self.currentNode)

    # On canvas click
    def onCanvasClick(self, event: tkinter.Event) -> None:
        canvas: tkinter.Canvas = event.widget
        x: int = canvas.canvasx(event.x)
        y: int = canvas.canvasy(event.y)
        elements = canvas.find_closest(x, y)

        if len(elements) > 0 and elements[0] in self.elementToNode:
            node = self.elementToNode[elements[0]]
            # find position back
            canvasInfo = self.nodeToCanvasInfo[node]
            if (abs(x - canvasInfo.x) > self.config.getint('tree_ui', 'moveX')) or \
                    (abs(y - canvasInfo.y) > self.config.getint('tree_ui', 'moveY')):
                return
            self.setCurrentNode(node)

    # on mistakes table click
    def onMistakesTableClick(self, values) -> None:
        if ('_analysis_stat_mistakes_table_' in values) and len(values['_analysis_stat_mistakes_table_']) > 0:
            ecoInfoWithNode: EcoInfoWithNode = self.mistakesTableInfo[values['_analysis_stat_mistakes_table_'][0]]
            self.window.FindElement('_analysis_mistake_variant_details_').Update(ecoInfoWithNode.ecoInfo.explanation())
            self.setCurrentNode(ecoInfoWithNode.node)

    # on bad results click
    def onBadResultsTableClick(self, values) -> None:
        if ('_analysis_stat_bad_results_table_' in values) and len(values['_analysis_stat_bad_results_table_']) > 0:
            ecoInfoWithNode: EcoInfoWithNode = self.badGamesTableInfo[values['_analysis_stat_bad_results_table_'][0]][0]
            self.window.FindElement('_analysis_bad_result_variant_details_').Update(
                ecoInfoWithNode.ecoInfo.explanation())
            self.setCurrentNode(ecoInfoWithNode.node)

    # on save mistakes game
    def onMistakesSave(self, values):
        if ('_analysis_stat_mistakes_table_' in values) and len(values['_analysis_stat_mistakes_table_']) > 0:
            ecoInfoWithNode: EcoInfoWithNode = self.mistakesTableInfo[values['_analysis_stat_mistakes_table_'][0]]
            node = ecoInfoWithNode.node
            out_file = '{}_mistake_{}_{}.pgn'.format(self.filename.split('.')[0], self.color, node.san())
            self.buildOutPgn([node], out_file)

    # on save bad results table
    def onBadResultsTableSave(self, values):
        if ('_analysis_stat_bad_results_table_' in values) and len(values['_analysis_stat_bad_results_table_']) > 0:
            index: int = values['_analysis_stat_bad_results_table_'][0]
            ecoInfoWithNode: EcoInfoWithNode = self.badGamesTableInfo[index][0]
            nodes_list: List[chess.pgn.GameNode] = self.badGamesTableInfo[index][1]
            out_file = '{}_badresults_{}_{}.pgn'.format(self.filename.split('.')[0], self.color,
                                                        ecoInfoWithNode.ecoInfo.ecoCode)
            self.buildOutPgn(nodes_list, out_file)

    ## Starts games analisys
    def onAnalyse(self) -> None:
        self.exitThread()
        if self.combinedGame is None:
            if not (self.buildCombinedPgn()):
                return
        self.showAnalisysTree()
        self.thread = threading.Thread(target=self.analyzeThread, args=())
        self.thread.start()
        self.window.FindElement('_operations_statistics_').Update(disabled=False)

    # Updates statistics tables
    def onStatistics(self, values) -> None:
        self.updateMistakesTable(values)
        self.updateBadResultsTable(values)

    # exits
    def exitThread(self) -> None:
        if self.thread is not None:
            with self.lock:
                self.stopThread = True
            self.thread.join()
            self.thread = None
            self.stopThread = False

    ## reacts on window event
    def onEvent(self, button, values) -> None:
        if button == '_operations_load_pgn_':
            self.loadPgnFile(values)

        if button == '_operations_refresh_filter_':
            self.refreshFilter(values)

        if button == '_operations_analyse_':
            self.onAnalyse()

        if button == '_operations_statistics_':
            self.onStatistics(values)

        if button == '_analysis_stat_mistakes_table_click_':
            self.onMistakesTableClick(values)

        if button == '_analysis_stat_bad_results_table_click_':
            self.onBadResultsTableClick(values)

        if button == 'analysis_stat_mistakes_save':
            self.onMistakesSave(values)

        if button == 'analysis_stat_bad_results_save':
            self.onBadResultsTableSave(values)

    ############################################## Analize thread ######################################################
    ## calculates the score in format we regular (pawns)  from engine output
    @staticmethod
    def calcScore(score):
        if score.is_mate():
            if score.turn == chess.WHITE:
                out_score = 1000.0
            else:
                out_score = -1000.0
        else:
            out_score = float((score.pov(chess.WHITE).score()) / 100.0)
        return out_score

    ## analyze thread - goes over combined game nodes in BFS order and analyzes them
    def analyzeThread(self):
        print('analyzeThread started')

        nodesList: List[chess.pgn.GameNode] = self.buildBFSNodesList()
        depth: int = self.config.getint('engine', 'depth')
        print('engineInfoThread: path to engine=', self.config.get('engine', 'enginePath'))
        engine = chess.engine.SimpleEngine.popen_uci(self.config.get('engine', 'enginePath'))

        i: int = 0
        nodesFromLastSave: int = 0
        with self.startOperation('Analyze', len(nodesList)) as operation:
            for node in nodesList:
                # check stop thread
                with self.lock:
                    if self.stopThread:
                        break

                # check if staticstics already upfated
                evalStats: Optional[EvaluationStats] = EvaluationStats.fromNode(node)
                chessBoard = node.board()
                if evalStats is None:
                    # get engine score
                    score: float = 0.0
                    with engine.analysis(chessBoard, options={'Contempt': 0}) as analisys:
                        for info in analisys:
                            if info.get('score') is not None and info.get('depth') > depth:
                                score = self.calcScore(info.get('score'))
                                break
                    nodesFromLastSave += 1
                    # calculate change
                    if node.move is not None:
                        parentEvalStats: Optional[EvaluationStats] = EvaluationStats.fromNode(node.parent)
                        assert (parentEvalStats is not None)
                        scoreChange = score - parentEvalStats.score
                    else:
                        scoreChange = 0.0
                    # update node with data
                    evalStats = EvaluationStats(score, scoreChange)
                    node.comment += evalStats.toCommentStr()
                i += 1
                move_color = chess.WHITE if chessBoard.turn == chess.BLACK else chess.BLACK
                move_classification = self.classifyMove(evalStats.change, move_color)
                try:
                    with self.lock:
                        if move_classification == MISTAKE:
                            self.mistakeNodes.append(node)
                        if move_classification == UNACCURACY:
                            self.unaccuracyNodes.append(node)

                        if node in self.nodeToCanvasInfo:
                            canvasInfo = self.nodeToCanvasInfo[node]
                            if canvasInfo.change_fill:
                                fill = self.moveClassToFillColor[move_classification]
                                self.analysisCanvas.itemconfig(canvasInfo.element, fill=fill)

                    operation.update(i)
                    if nodesFromLastSave > self.config.getint('engine', 'analyzedMovesToSave'):
                        self.saveCombinedPgn()
                        operation.update(i)
                        nodesFromLastSave = 0
                except:
                    pass

        engine.quit()
        try:
            self.saveCombinedPgn()
        except:
            pass
        print('Analysis thread EXIT')
