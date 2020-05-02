# GamesAnalyzer

Project to prepare to chess game against specific opponent as well for analyzing self games.
Provides download of pgn archive from chess-db, lichess or chess.com and then automatically analyzes them.
Draws games variation tree with different coloring for mistakes and unaccuracies. 
Provides statistics - for what theoratical variations lost percantage were high, and typical mistakes.

<br>**Before running**:<br>
Update config.cfg with following parameters:<br> 
1. _engine.enginePath_ - path to engine <br>
2. lichess.tokenFile - file contains API token for lichess (can be generated at https://lichess.org/account/oauth/token)

<br>**Project files**<br>
_chessBordUI.py_ - responsible for chess board UI <br>
_dataBaseTab.py_ - responcible for downloading pgn archive (from chess-db, chess.com or lichess)<br>
_mainGame.py_ - main module <br>
_analysisTab.py_ - for analysis features and tabs <br>

<br>**Packages used**<br> 
The following packages are used for development: <br/>
    1.PySimpleGUI (https://pysimplegui.readthedocs.io/en/latest/) package for UI development<br>
    2.Python-chess (https://python-chess.readthedocs.io/en/latest/index.html) package for chess manipulations<br>
    3.berserk - API for lichess (https://berserk.readthedocs.io/en/master/api.html) <br>
    4.Used chess pieces and code from PySimpleGUI chess sample in https://github.com/PySimpleGUI/PySimpleGUI/tree/master/Chess


  
       