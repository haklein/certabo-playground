# UCI engine for CERTABO usb chess board (eboard)

This UCI engine allows to use the CERTABO eboard with any chess software that supports UCI engines. It's a proof of concept and probably still has some rough edges.

A short video showing some of the features can be found here:
https://youtu.be/qETHjeTY-SY

## Getting started

### Prerequisites

You have to do the calibration with the CERTABO software once. This will then be loaded by the UCI engine.

### pychess

Just add it as engine in pychess. I've added a wrapper script (`uci.sh`) to specify the port as parameter (`--port /dev/ttyUSB0` in my case).

### lichess bot

This has also been used successfully with the official lichess bot: https://github.com/careless25/lichess-bot
Just specify the engine in the `config.yaml`. Then you can play on lichess with the CERTABO eboard (be aware that your account needs to be a bot account).

## Todo

* shake out bugs
* clean up logging (very chatty for now)

## License

This project is licensed under the GPL v3 license

## Acknowledgments

* the UCI parser was taken from the sunfish engine: https://github.com/thomasahle/sunfish
* thanks to CERTABO for being very open about their boards (open source software, simple protocol, arduino simulator)
