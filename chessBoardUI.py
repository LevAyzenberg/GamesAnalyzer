import configparser
import chess
import PySimpleGUI as sg
import threading
import os
import copy

class ChessBoardUI :
    def __init__(self,configFile) :
        config = configparser.RawConfigParser()
        config.read(configFile)
        piecesPath=config.get('chessBoard','piecesPath')

        blank = os.path.join(piecesPath, config.get('chessBoard','blank'))
        bishopB = os.path.join(piecesPath, config.get('chessBoard','bishopB'))
        bishopW = os.path.join(piecesPath, config.get('chessBoard','bishopW'))
        pawnB = os.path.join(piecesPath, config.get('chessBoard','pawnB'))
        pawnW = os.path.join(piecesPath, config.get('chessBoard','pawnW'))
        knightB = os.path.join(piecesPath, config.get('chessBoard','knightB'))
        knightW = os.path.join(piecesPath, config.get('chessBoard','knightW'))
        rookB = os.path.join(piecesPath, config.get('chessBoard','rookB'))
        rookW = os.path.join(piecesPath, config.get('chessBoard','rookW'))
        queenB = os.path.join(piecesPath, config.get('chessBoard','queenB'))
        queenW = os.path.join(piecesPath, config.get('chessBoard','queenW'))
        kingB = os.path.join(piecesPath, config.get('chessBoard','kingB'))
        kingW = os.path.join(piecesPath, config.get('chessBoard','kingW'))

        # map from pieces (in chess respresentation) to images 
        self.images = {
            (chess.BISHOP,chess.BLACK): bishopB,
            (chess.BISHOP,chess.WHITE): bishopW,
            (chess.PAWN,chess.BLACK): pawnB,
            (chess.PAWN,chess.WHITE): pawnW,
            (chess.KNIGHT,chess.BLACK): knightB,
            (chess.KNIGHT,chess.WHITE): knightW,
            (chess.ROOK,chess.BLACK): rookB,
            (chess.ROOK,chess.WHITE): rookW,
            (chess.KING,chess.BLACK): kingB,
            (chess.KING,chess.WHITE): kingW,
            (chess.QUEEN,chess.BLACK): queenB,
            (chess.QUEEN,chess.WHITE) : queenW,
            (None,None) : blank
        }

        self.empty_board=[
            [[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None]],
            [[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None]],
            [[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None]],
            [[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None]],
            [[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None]],
            [[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None]],
            [[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None]],
            [[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None],[None,None]]
        ]
        self.chessBoard=None
        self.flipped=False

    def redrawBoard(self, window, chessBoard):
        ## Render board
        board = self.chessBoardToUI(chessBoard, self.flipped)
        # try:
        for i in range(8):
            for j in range(8):
                color = '#B58863' if (i + j) % 2 else '#F0D9B5'

                piece_image = self.images[tuple(board[i][j])]
                elem = window.FindElement(key=(i, j))
                elem.Update(piece_image)
                elem.Widget.configure(background=color)
        self.chessBoard=chessBoard

    ## Stops UI thread
    def stopUI(self):
        print('UI stopped')

    ## Transfers UI coordinates to chess notation
    def fromGuiToChess(self,coord,flipped) :
        if flipped:
            return coord[0]*8+7-coord[1]
        else :
            return (7-coord[0])*8 + coord[1]

    ## Transfers chess notation to UI coordinates
    def fromChessToGui(self, square,flipped) :
        coord=[int((chess.H8-square)/8),square%8]
        if flipped:
            return [7-coord[0],7-coord[1]]
        else :
            return coord

    ## Transfer board to UI view
    def chessBoardToUI(self,chessBoard,flipped) :
        uiBoard=self.empty_board
        for i in range(chess.A1, chess.H8+1) :
            uiCoord=self.fromChessToGui(i,flipped)
            uiBoard[uiCoord[0]][uiCoord[1]]=[chessBoard.piece_type_at(i),chessBoard.color_at(i)]
        return uiBoard

    ## Renders specifc square for initial board tab
    def renderSquare(self, image, key, location):
        if (location[0] + location[1]) % 2:
            color = '#B58863'
        else:
            color = '#F0D9B5'
        return sg.Image(image, size=(40, 40), background_color=color, pad=(0, 0), key=key)


    ## creates initial board Tab
    def createBoardTab(self,chessBoard) :
        initial_board =self.chessBoardToUI(chessBoard,False)
    
        # the main board display layout
        board_layout = [[sg.T('      ')] + [sg.T('{}'.format(a), pad=((4,27),0), font='Any 13',key='_upper_letters_'+str(ord(a)-ord('a'))) for a in 'abcdefgh']]
        # loop though board and create buttons with images
        for i in range(8):
            row = [sg.T(str(8-i)+' ', font='Any 13',key='left_number'+str(i))]
            for j in range(8):
                piece_image = self.images[tuple(initial_board[i][j])]
                row.append(self.renderSquare(piece_image, key=(i,j), location=(i,j)))
            row.append(sg.T(str(8-i)+' ', font='Any 13',key='right_number'+str(i)))
            board_layout.append(row)
        # add the labels across bottom of board
        board_layout.append([sg.T('      ')] + [sg.T('{}'.format(a), pad=((4,27),0), font='Any 13',key='_lower_letters_'+str(ord(a)-ord('a'))) for a in 'abcdefgh'])
        self.chessBoard=chessBoard

        return [[sg.Column(board_layout)]]

    def onEvent(self, window, button, value) :
        if button == 'Flip':
            self.flipped= not(self.flipped)
            if self.flipped :
                lettersRange='hgfedcba'
                numbersRange='12345678'
            else:
                lettersRange='abcdefgh'
                numbersRange='87654321'

            for i in range(0,8) :
                window.FindElement('_upper_letters_'+str(i)).Update(lettersRange[i])
                window.FindElement('_lower_letters_'+str(i)).Update(lettersRange[i])
                window.FindElement('left_number'+str(i)).Update(numbersRange[i]+' ')
                window.FindElement('right_number'+str(i)).Update(numbersRange[i]+' ')

            self.redrawBoard(window,self.chessBoard)
            

