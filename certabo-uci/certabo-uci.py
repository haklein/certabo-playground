#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# based on the sunfish uci code from Thomas Ahle & Contributors  - https://github.com/thomasahle/sunfish
# 

from __future__ import print_function
from __future__ import division
import importlib
import re
import sys
import time
import logging
import logging.handlers
import traceback
import os
import argparse
import subprocess
import time as tt
import threading
import queue
import serial
import fcntl

import serial.tools.list_ports

from socket import *
from select import *

import chess.pgn
import chess

from random import shuffle

import codes

from utils import port2number, port2udp, find_port, get_engine_list, get_book_list, coords_in
from constants import CERTABO_SAVE_PATH, CERTABO_DATA_PATH, MAX_DEPTH_DEFAULT

DEBUG = True

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(module)s %(message)s')

filehandler = logging.handlers.TimedRotatingFileHandler(
    os.path.join(CERTABO_DATA_PATH, "certabo-uci.log"), backupCount=12
)
filehandler.setFormatter(formatter)
logger.addHandler(filehandler)

# log unhandled exceptions to the log file
def my_excepthook(excType, excValue, traceback, logger=logger):
    logger.error("Uncaught exception",
                 exc_info=(excType, excValue, traceback))
sys.excepthook = my_excepthook

logging.info("certabi-uci.py startup")

for d in (CERTABO_SAVE_PATH, CERTABO_DATA_PATH):
    try:
        os.makedirs(d)
    except OSError:
        pass

parser = argparse.ArgumentParser()
parser.add_argument("--port")
# ignore additional parameters
# parser.add_argument('bar', nargs='?')
args = parser.parse_args()

portname = 'auto'
if args.port is not None:
    portname = args.port
port = port2number(portname)

stack = queue.Queue()
serial_in = queue.Queue()
serial_out = queue.Queue()

class ucireader(threading.Thread):
    def __init__ (self, device='sys.stdin'):
        threading.Thread.__init__(self)
        self.device = device

    def run(self):
        while True:
            try:
                line = input() # we ignore the specific device and just read via input() from stdin
                stack.put(line)
                if line == "quit":
                    break
            except EOFError:
                # we quit
                stack.put('quit')
                break

inputthread = ucireader('sys.stdin')
inputthread.daemon = True
inputthread.start()

class serialreader(threading.Thread):
    def __init__ (self, device='auto'):
        threading.Thread.__init__(self)
        self.device = device
        self.connected = False

    def run(self):
        while True:
            if not self.connected:
                try:
                    if self.device == 'auto':
                        logging.info(f'Auto-detecting serial port')
                        serialport = find_port()
                    else:
                        serialport = self.device
                    if serialport is None:
                        logging.info(f'No port found, retrying')
                        time.sleep(1)
                        continue
                    logging.info(f'Opening serial port {serialport}')
                    uart = serial.Serial(serialport, 38400, timeout=2.5)  # 0-COM1, 1-COM2 / speed /
                    logging.debug(f'Attempting to lock {serialport}')
                    fcntl.flock(uart.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logging.debug(f'Flushing input on {serialport}')
                    uart.flushInput()
                    self.connected = True
                except Exception as e:
                    logging.info(f'ERROR: Cannot open serial port {serialport}: {str(e)}')
                    self.connected = False
                    time.sleep(0.1)
            else:
                try:
                    while uart.inWaiting():
                        # logging.debug(f'serial data pending')
                        message = uart.readline().decode("ascii")
                        message = message[1: -3]
                        #if DEBUG:
                        #    print(len(message.split(" ")), "numbers")
                        if len(message.split(" ")) == 320:  # 64*5
                            serial_in.put(message)
                        message = ""
                    time.sleep(0.001)
                    if not serial_out.empty():
                        data = serial_out.get()
                        serial_out.task_done()
                        logging.debug(f'Sending to serial: {data}')
                        uart.write(data)
                except Exception as e:
                    logging.info(f'Exception during serial communication: {str(e)}')
                    self.connected = False

def main():
    global portname
    new_usb_data = False
    usb_data_exist = False
    serial_thread_spawned = False

    def send_leds(message=b'\x00' * 8):
        serial_out.put(message)

    chessboard = chess.Board()
    tmp_chessboard = chess.Board()
    move = []
    starting_position = chess.STARTING_FEN
    rotate180 = False
    mystate = "init"

    calibration = False
    new_setup = True
    calibration_samples_counter = 0
    calibration_samples = []

    usb_data_history_depth = 3
    usb_data_history = list(range(usb_data_history_depth))
    usb_data_history_filled = False
    usb_data_history_i = 0
    move_detect_tries = 0
    move_detect_max_tries = 3

    #out = Unbuffered(sys.stdout)
    # out = sys.stdout
    def output(line):
        logging.debug(f'<<< {line} ')
        print(line)
        sys.stdout.flush()
        #print(line, file=out)
        # print('\n', file=out)
        # logging.debug(line)

    while True:
        ucicommand = ""

        time.sleep(0.001)
        # logging.debug(f'testing for items in serial_in queue')
        if not serial_in.empty():
            try:
                data = serial_in.get()
                serial_in.task_done()
                # logging.debug(f'serial data received from serial_in queue: {data}')
                usb_data = list(map(int, data.split(" ")))
                new_usb_data = True
                usb_data_exist = True
                # logging.debug(f'data from usb {usb_data}')

            except Exception as e:
                logging.info(f'No new data from usb, perhaps chess board not connected: {str(e)}')

        if calibration == True and new_usb_data == True:
            calibration_samples.append(usb_data)
            new_usb_data = False 
            logging.info("    adding new calibration sample")
            calibration_samples_counter += 1
            if calibration_samples_counter %2:
                send_leds(b'\xff\xff\x00\x00\x00\x00\xff\xff')
            else:
                send_leds()
            if calibration_samples_counter >= 15:
                logging.info(
                    "------- we have collected enough samples for averaging ----"
                )
                usb_data = codes.statistic_processing_for_calibration(
                    calibration_samples, False
                )
                codes.calibration(usb_data, new_setup, port)
                calibration = False
                output('readyok') # as calibration takes some time, we safely(?) assume that "isready" has already been sent, so we reply readyness
                send_leds()

        if not stack.empty():
            logging.debug(f'getting uci command from stack')
            ucicommand = stack.get()
            stack.task_done()
            logging.debug(f'>>> {ucicommand} ')

            if ucicommand == 'quit':
                break

            elif ucicommand == 'uci':
                output('id name CERTABO physical board')
                output('id author Harald Klein (based on work from Thomas Ahle & Contributors)')
                output('option name Calibrate type check default false')
                output('option name AddPiece type check default false')
                output('option name Rotate type check default false')
                output('option name Port type string default auto')
                output('uciok')

            elif ucicommand == 'isready':
                if not serial_thread_spawned:
                    serial_thread_spawned = True
                    serialthread = serialreader(portname)
                    serialthread.daemon = True
                    serialthread.start()
                    codes.load_calibration(port)
                    # make some nice blinky
                    send_leds(codes.squareset2ledbytes(chess.SquareSet(chess.BB_LIGHT_SQUARES)))
                    time.sleep(1)
                    send_leds(codes.squareset2ledbytes(chess.SquareSet(chess.BB_DARK_SQUARES)))
                    time.sleep(1)
                    send_leds()

                if not calibration:
                    output('readyok')

            elif ucicommand == 'ucinewgame':
                logging.debug("new game")

            elif ucicommand.startswith('setoption name Port value'):
                _, _, _, _, tmp_portname = ucicommand.split(' ', 4)
                logging.info(f"Setoption Port received: {tmp_portname}")
                portname = tmp_portname

            elif ucicommand.startswith('setoption name AddPiece value true'):
                logging.info("Adding new pieces to existing calibration")
                calibration = True
                new_setup = False

            elif ucicommand.startswith('setoption name Calibrate value true'):
                logging.info("Calibrating board")
                calibration = True

            elif ucicommand.startswith('setoption name Rotate value true'):
                logging.info("Rotating board")
                rotate180 = True

            elif ucicommand.startswith('position'):
                if 'startpos' in ucicommand:
                    logging.info(f'position startpos received')
                    tmp_chessboard = chess.Board()
                elif 'fen' in ucicommand:
                    _, _, fen  = ucicommand.split(' ',2)
                    if ' moves ' in fen:
                        fen = fen.split(' moves ')[0]
                    logging.info(f'position fen received: {fen}')
                    tmp_chessboard = chess.Board(fen)
                else:
                    logging.info(f'ERROR: position received without either startpos keyword or fen. Assuming startpos.')
                    tmp_chessboard = chess.Board()

                if ' moves ' in ucicommand:
                    moves = ucicommand.split(' moves ')[1].split(' ')
                    logging.info(f'position contains moves: {moves}')
                    for move in moves:
                        logging.debug(f'pushing move: {move}')
                        tmp_chessboard.push_uci(move)

                logging.info(f'position board state: {tmp_chessboard.fen()}')

            elif ucicommand.startswith('go'):
                logging.debug("go...")
                possible_moves = list(chessboard.legal_moves)
                logging.debug(f'legal moves: {possible_moves}')
                if tmp_chessboard.fen() == chess.STARTING_FEN:
                    # we did receive a starting FEN, so it is our turn and we're white
                    logging.info(f'we received a starting FEN, we are white and it is our turn')
                    mystate = "user_shall_place_his_move"
                else:
                    try:
                        new_move = codes.get_moves(chessboard, tmp_chessboard.fen)
                        logging.info(f'bot opponent played: {new_move}')
                        chessboard = tmp_chessboard
                        mystate = "user_shall_place_oppt_move"
                    except:
                        logging.debug(f'cannot find move, assume new game from FEN')
                        chessboard = tmp_chessboard
                        mystate = "user_shall_place_his_move"

            else:
                logging.debug(f'unhandled: {ucicommand}')
                pass
        
        if new_usb_data:
            new_usb_data = False

            if usb_data_history_i >= usb_data_history_depth:
                usb_data_history_filled = True
                usb_data_history_i = 0

            usb_data_history[usb_data_history_i] = list(usb_data)[:]
            usb_data_history_i += 1
            if usb_data_history_filled:
                usb_data_processed = codes.statistic_processing(usb_data_history, False)
                if usb_data_processed != []:
                    test_state = codes.usb_data_to_FEN(usb_data_processed, rotate180)
                    if test_state != "":
                        board_state_usb = test_state
                        # output(f'info string FEN {board_state_usb}')
                        # compare virtual board state and state from usb
                        s1 = chessboard.board_fen()
                        s2 = board_state_usb.split(" ")[0]
                        if (s1 != s2) and (mystate != 'init'):
                            if mystate == "user_shall_place_oppt_move":
                                try:
                                    move_detect_tries += 1
                                    move = codes.get_moves(chessboard, board_state_usb)
                                except codes.InvalidMove:
                                    diffmap = codes.diff2squareset(s1, s2)
                                    logging.debug(f'Difference on Squares:\n{diffmap}')
                                    send_leds(codes.squareset2ledbytes(diffmap))

                                    if move_detect_tries > move_detect_max_tries:
                                        logging.info("Invalid move")
                                    else:
                                        move_detect_tries = 0
                                if move:
                                    send_leds(codes.move2ledbytes(move, rotate180))
                                    logging.info(f'moves difference: {move}')
                                    logging.info("move for opponent")
                                    output(f'info string move for opponent')
                            elif mystate == "user_shall_place_his_move":
                                try:
                                    move_detect_tries += 1
                                    move = codes.get_moves(chessboard, board_state_usb)
                                    logging.debug(f'moves difference: {move}')
                                    logging.debug(f'move count: {len(move)}')
                                    if len(move) == 1:
                                        # single move
                                        bestmove = move[0]
                                        legal_moves = list(chessboard.legal_moves)
                                        logging.debug(f'valid moves {legal_moves}')
                                        if chess.Move.from_uci(bestmove) in list(chessboard.legal_moves):
                                            logging.debug('valid move')
                                        else:
                                            logging.debug('invalid move')
                                        logging.info("user moves")
                                        chessboard.push_uci(bestmove)
                                        output(f'bestmove {bestmove}')
                                        mystate = "init"
                                except codes.InvalidMove:
                                    diffmap = codes.diff2squareset(s1, s2)
                                    logging.debug(f'Difference on Squares:\n{diffmap}')
                                    send_leds(codes.squareset2ledbytes(diffmap))

                                    if move_detect_tries > move_detect_max_tries:
                                        logging.info("Invalid move")
                                    else:
                                        move_detect_tries = 0

                            else:
                                diffmap = codes.diff2squareset(s1, s2)
                                logging.debug(f'Difference on Squares:\n{diffmap}')
                                send_leds(codes.squareset2ledbytes(diffmap))
                                output(f'info string place pieces on their places')
                                if DEBUG:
                                    logging.info("Place pieces on their places")
                                    logging.info("Virtual board: %s", chessboard.fen())
                        else: # board is the same
                            if mystate == "user_shall_place_oppt_move":
                                logging.info("user has moved opponent, now it's his own turn")
                                mystate = "user_shall_place_his_move" 
                            send_leds()

if __name__ == '__main__':
    main()

