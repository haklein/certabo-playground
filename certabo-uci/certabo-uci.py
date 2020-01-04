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

logging.basicConfig(filename='/dev/null', level=logging.DEBUG, format='%(process)d %(asctime)s %(levelname)s %(module)s  %(message)s')
logger = logging.getLogger()
filehandler = logging.handlers.TimedRotatingFileHandler(
    os.path.join(CERTABO_DATA_PATH, "certabo-uci.log"), backupCount=12
)
logger.addHandler(filehandler)


for d in (CERTABO_SAVE_PATH, CERTABO_DATA_PATH):
    try:
        os.makedirs(d)
    except OSError:
        pass

parser = argparse.ArgumentParser()
parser.add_argument("--port")
args = parser.parse_args()

portname = 'auto'
if args.port is not None:
    portname = args.port
port = port2number(portname)

stack = queue.Queue()
serial_in = queue.Queue()
serial_out = queue.Queue()

interrupted = threading.Lock()
interrupted.acquire()

class ucireader(threading.Thread):
    def __init__ (self, device='sys.stdin'):
        threading.Thread.__init__(self)
        self.device = device

    def run(self):
        while not interrupted.acquire(blocking=False):
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
inputthread.start()


interrupted_serial = threading.Lock()
interrupted_serial.acquire()

class serialreader(threading.Thread):
    def __init__ (self, device='auto'):
        threading.Thread.__init__(self)
        self.device = device
        self.connected = False

    def run(self):
        while not interrupted_serial.acquire(blocking=False):
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
                    logging.info(f'Attempting to lock {serialport}')
                    fcntl.flock(uart.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logging.info(f'Flushing input on {serialport}')
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


# Disable buffering
class Unbuffered(object):
    def __init__(self, stream):
        self.stream = stream
    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        #sys.stderr.write(data)
        #sys.stderr.flush()
        logging.debug(f'<<< {data} ')
    def __getattr__(self, attr):
        return getattr(self.stream, attr)

def main():
    global portname
    new_usb_data = False
    usb_data_exist = False
    serial_thread_spawned = False

    def send_leds(message=b'\x00' * 8):
        serial_out.put(message)

    chessboard = chess.Board()
    board_state = chessboard.fen()
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

    out = Unbuffered(sys.stdout)
    # out = sys.stdout
    def output(line):
        print(line, file=out)
        # print('\n', file=out)
        sys.stdout.flush()
        # logging.debug(line)

    while True:
        smove = ""

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
            smove = stack.get()
            stack.task_done()
            logging.debug(f'>>> {smove} ')

            if smove == 'quit':
                break

            elif smove == 'uci':
                output('id name CERTABO physical board')
                output('id author Harald Klein (based on work from Thomas Ahle & Contributors)')
                output('option name Calibrate type check default false')
                output('option name AddPiece type check default false')
                output('option name Rotate type check default false')
                output('option name Port type string default auto')
                output('uciok')

            elif smove == 'isready':
                if  not serial_thread_spawned:
                    serial_thread_spawned = True
                    serialthread = serialreader(portname)
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

            elif smove == 'ucinewgame':
                logging.debug("new game")
                # stack.append('position fen ...')

            elif smove.startswith('setoption name Port value'):
                _, _, _, _, tmp_portname = smove.split(' ', 4)
                logging.info(f"Setoption Port received: {tmp_portname}")
                portname = tmp_portname

            elif smove.startswith('setoption name AddPiece value true'):
                logging.info("Adding new pieces to existing calibration")
                calibration = True
                new_setup = False

            elif smove.startswith('setoption name Calibrate value true'):
                logging.info("Calibrating board")
                calibration = True

            elif smove.startswith('setoption name Rotate value true'):
                logging.info("Rotating board")
                rotate180 = True

            elif smove.startswith('position fen'):
                _, _, fen = smove.split(' ', 2)
                logging.debug(f'fen: {fen}')

            elif smove.startswith('position startpos'):
                parameters = smove.split(' ')
                logging.debug(f'startpos received {parameters}')

                #logging.info(f'{len(parameters)}')
                if len(parameters)>2:
                    if parameters[2] == 'moves':
                        tmp_chessboard = chess.Board()
                        for move in parameters[3:]:
                            logging.debug(f'move: {move}')
                            tmp_chessboard.push_uci(move)
                        board_state = tmp_chessboard.fen()
                        logging.debug(f'startpos board state: {board_state}')
                        new_move = codes.get_moves(chessboard, board_state)
                        logging.info(f'bot opponent played: {new_move}')
                        chessboard = tmp_chessboard
                        mystate = "user_shall_place_oppt_move"
                else:
                    # we did receive a startpos without any moves, so we're probably white and it's our turn
                    chessboard = chess.Board()
                    # if chessboard.turn == chess.WHITE: 
                    logging.debug(f'startpos board state: {board_state}')
                    mystate = "user_shall_place_his_move"
                    logging.info(f'we are white, it is our turn')

            elif smove.startswith('go'):
                logging.debug("go...")
                # output('resign')
                possible_moves = list(chessboard.legal_moves)
                logging.debug(f'legal moves: {possible_moves}')
                #logging.debug(f'legal move: {possible_moves[0]}')
                #output('currmove e7e5')
                #shuffle(possible_moves)
                #output(f'bestmove {possible_moves[0]}')

            else:
                logging.debug(f'unhandled: {smove}')
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
                        game_process_just_started = False

                        # compare virtual board state and state from usb
                        s1 = chessboard.board_fen()
                        s2 = board_state_usb.split(" ")[0]
                        if s1 != s2:
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

    # we quit, stop input thread
    interrupted.release()
    interrupted_serial.release()

if __name__ == '__main__':
    main()

