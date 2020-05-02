import PySimpleGUI as sg
import chess
import chess.pgn
from dataBaseTab import DatabaseTab
from analysisTab import AnalysisTab
from chessBoardUI import ChessBoardUI

CONFIG_FILE = 'config.cfg'


def playGame():
    menu_def = [['&File', ['&Open', 'Open &Combined Pgn', 'E&xit']], ['&Board', ['&Flip']]]
    sg.ChangeLookAndFeel('BrownBlue')
    chess_board = chess.pgn.Game().board()
    # create initial board setup
    chessBoardUI = ChessBoardUI(CONFIG_FILE)
    databaseTab = DatabaseTab(CONFIG_FILE)
    analysisTab = AnalysisTab(CONFIG_FILE, lambda chessBoard: chessBoardUI.redrawBoard(window, chessBoard))

    # the main window layout
    layout = [[sg.Menu(menu_def, tearoff=False)],
              [sg.Column([
                  [databaseTab.getTab()],
                  [analysisTab.getOperationsTab()],
                  [sg.Frame(title='Board', layout=chessBoardUI.createBoardTab(chess_board)),
                   sg.Column([[analysisTab.getAnalyzeTreeTab()]])]]),
                  analysisTab.getAnalysisResultsTab()]]

    window = sg.Window('Chess', default_button_element_size=(12, 1), auto_size_buttons=False, icon='kingb.ico',
                       return_keyboard_events=True, resizable=True).Layout(layout)
    window.Finalize()
    databaseTab.onWindowFinalize(window)
    analysisTab.onWindowFinalize(window)

    # ---===--- Loop taking in user input --- #
    while True:
        button, value = window.Read()

        if button == 'Exit':
            window.Close()
            break

        if button is None:
            break

        # Menu and buttons evaluation
        if button == 'Open':
            filename = sg.PopupGetFile('Open database', title='Open database', no_window=True, default_extension="pgn",
                                       file_types=(('PGN Files', '*.pgn'),))
            if filename is not None and filename != '':
                analysisTab.setFilename(filename)
            else:
                print('Cancel')

        if button == 'Open Combined Pgn':
            filename = sg.PopupGetFile('Open combined database', title='Open combined database', no_window=True,
                                       default_extension="pgn",
                                       file_types=(('PGN Files', '*.pgn'),))
            if filename is not None and filename != '':
                analysisTab.setCombinedFilename(filename, value)
            else:
                print('Cancel')

        info = databaseTab.onEvent(window, button)
        if info is not None:
            analysisTab.setFilename(info.filename)
            analysisTab.setDates(info.fromDate, info.tillDate)

        analysisTab.onEvent(button, value)

        # check events in engine tab class
        chessBoardUI.onEvent(window, button, value)

    analysisTab.exitThread()
    chessBoardUI.stopUI()
    print("EXIT\n")


playGame()
