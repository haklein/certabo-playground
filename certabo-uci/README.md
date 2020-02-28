# UCI engine for CERTABO usb chess board (eboard)

This UCI engine allows to use the CERTABO eboard with any chess software that supports UCI engines. It's a proof of concept and probably still has some rough edges.

A short video showing some of the features can be found here:
https://youtu.be/qETHjeTY-SY

## Getting started

### Prerequisites

You have to do the calibration once. This will then be loaded by the UCI engine on subsequent runs. When you want to add more pieces (e.g. 2nd pair of queens),
just use the "AddPiece" option and replace the existing queens with the new ones before start of the engine. You only need to do that once, all added pieces
will be stored in the calibration file. You can add as many sets as you want. A new calibration will reset to scratch.

## Chess GUIs

### pychess

Just add it as engine in pychess and select it as one of the opponents.

### lichess bot

This has also been used successfully with the official lichess bot: https://github.com/careless25/lichess-bot
Just specify the engine in the `config.yaml`. Then you can play on lichess with the CERTABO eboard (be aware that your account needs to be a bot account). If you want to play on lichess with a human account, you might be interested in https://github.com/haklein/certabo-playground/tree/master/certabo-lichess

### Arena 3.9 Beta (Linux)

Just add the engine and use it as one of the engines in a tournament.

### jcchess

Just add the engine and select it as player.

### SCID vs PC

Add the engine in a two engine tournament with a single game

## Todo

* shake out bugs
* clean up logging (very chatty for now)

## License

This project is licensed under the GPL v3 license

## Acknowledgments

* the UCI parser was taken from the sunfish engine: https://github.com/thomasahle/sunfish
* thanks to CERTABO for being very open about their boards (open source software, simple protocol, arduino simulator)
