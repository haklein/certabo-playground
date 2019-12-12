# UCI engine for CERTABO usb chess board (eboard)

This UCI engine allows to use the CERTABO eboard with any chess software that supports UCI engine. It's a proof of concept and probably still has some rough edges.

## Getting started

### Prerequisites

You have to do the calibration with the CERTABO software once. This will then be loaded by the UCI engine.

### pychess

Just add it as engine in pychess. I've added a wrapper script (`uci.sh`) to specify the port as parameter (`--port /dev/ttyUSB0` in my case).

### lichess bot

This has also been used successfully with the official lichess bot: https://github.com/careless25/lichess-bot
Just specify the engine in the config yaml. Then you can play on lichess with the CERTABO eboard (be aware that your account needs to be a bot account).

## Todo

* shake out bugs
* clean up logging (very chatty for now)
* enable calibration via UCI setting
* verify validity of user move, to make sure we don't send an invalid move as UCI `bestmove`. Set LEDs in a way that user can easily revert invalid move.

## License

This project is licensed under the GPL v3 license

## Acknowledgments

* the UCI parser was inspired (and partially copied) by the sunfish engine: https://github.com/thomasahle/sunfish
* Certabo for being very open about their boards (open source software, simple protocol, arduino simulator)
