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
import os
import argparse
import subprocess
import time as tt

from socket import *
from select import *

import chess.pgn
import chess

from random import shuffle

import codes

DEBUG_FAST = False
DEBUG = True

logging.basicConfig(filename='uci.log', level=logging.DEBUG)

from utils import port2number, port2udp, find_port, get_engine_list, get_book_list, coords_in
from constants import CERTABO_SAVE_PATH, CERTABO_DATA_PATH, MAX_DEPTH_DEFAULT

for d in (CERTABO_SAVE_PATH, CERTABO_DATA_PATH):
    try:
        os.makedirs(d)
    except OSError:
        pass

parser = argparse.ArgumentParser()
parser.add_argument("--port")
args = parser.parse_args()

if args.port is None:
    portname = find_port()
else:
    portname = args.port
port = port2number(portname)

board_listen_port, gui_listen_port = port2udp(port)
logging.info('GUI: Board listen port: %s, gui listen port: %s', board_listen_port, gui_listen_port)

SEND_SOCKET = ("127.0.0.1", board_listen_port)  # send to
LISTEN_SOCKET = ("127.0.0.1", gui_listen_port)  # listen to

TO_EXE = getattr(sys, "frozen", False)

if TO_EXE:
    if platform.system() == "Windows":
        usb_command = ["usbtool.exe"]
    else:
        usb_command = ["./usbtool"]
else:
    usb_command = ["python2", "usbtool.py"]
if portname is not None:
    usb_command.extend(["--port", portname])
logging.debug("Calling %s", usb_command)
usb_proc = subprocess.Popen(usb_command)

if not DEBUG_FAST:
    tt.sleep(1)  # time to make stable COMx connection

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
    chessboard = chess.Board()
    board_state = chessboard.fen()
    move = []
    starting_position = chess.STARTING_FEN
    waiting_for_user_move = False
    rotate180 = False

    sock = socket(AF_INET, SOCK_DGRAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(LISTEN_SOCKET)
    sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
    recv_list = [sock]
    new_usb_data = False
    usb_data_exist = False

    codes.load_calibration(port)
    calibration = False
    calibration_samples_counter = 0
    calibration_samples = []

    usb_data_history_depth = 3
    usb_data_history = list(range(usb_data_history_depth))
    usb_data_history_filled = False
    usb_data_history_i = 0
    move_detect_tries = 0
    move_detect_max_tries = 3

    calibration = True



    out = Unbuffered(sys.stdout)
    # out = sys.stdout
    def output(line):
        print(line, file=out)
        # print('\n', file=out)
        sys.stdout.flush()
        # logging.debug(line)

    stack = []
    while True:
        smove = ""
        recv_ready, wtp, xtp = select(recv_list, [], [], 0.002)

        if recv_ready:
            try:
                data, addr = sock.recvfrom(2048)
                usb_data = list(map(int, data.decode().split(" ")))
                new_usb_data = True
                usb_data_exist = True
                # logging.debug(f'data from usb {usb_data}')

            except:
                logging.info("No new data from usb, perhaps chess board not connected")

        if stack:
            smove = stack.pop()
        else:
            if select([sys.stdin,],[],[],0.0)[0]:
                smove = input()
                logging.debug(f'>>> {smove} ')

                if smove == 'quit':
                    break

                elif smove == 'uci':
                    output('id name CERTABO physical board')
                    output('id author Harald Klein (based on work from Thomas Ahle & Contributors)')
                    output('uciok')

                elif smove == 'isready':
                    output('readyok')

                elif smove == 'ucinewgame':
                    logging.debug("new game")
                    # stack.append('position fen ...')

                elif smove.startswith('position fen'):
                    _, _, fen = smove.split(' ', 2)
                    logging.debug("fen: ", fen)

                elif smove.startswith('position startpos'):
                    parameters = smove.split(' ')
                    logging.debug(f'startpos received {parameters}')

                    chessboard.reset()
                    if parameters[2] == 'moves':
                        for move in parameters[3:]:
                            logging.debug(f'move: {move}')
                            chessboard.push_uci(move)
                    board_state = chessboard.fen()
                    logging.debug(f'board state: {board_state}')


                elif smove.startswith('go'):
                    logging.debug("go...")
                    waiting_for_user_move = True
                    # output('resign')
                    possible_moves = list(chessboard.legal_moves)
                    logging.debug(f'legal moves: {possible_moves}')
                    #logging.debug(f'legal move: {possible_moves[0]}')
                    #output('currmove e7e5')
                    #shuffle(possible_moves)
                    #output(f'bestmove {possible_moves[0]}')

                else:
                    logging.debug(f'unandled: {smove}')
                    pass
        
        if new_usb_data:
            new_usb_data = False
            if DEBUG:
                logging.info("Virtual board: %s", chessboard.fen())

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
                           if waiting_for_user_move:
                                try:
                                    move_detect_tries += 1
                                    move = codes.get_moves(chessboard, board_state_usb)
                                except codes.InvalidMove:
                                    if move_detect_tries > move_detect_max_tries:
                                        logging.info("Invalid move")
                                else:
                                    move_detect_tries = 0
                                    if move:
                                        waiting_for_user_move = False
                                        do_user_move = True
                                        output(f'bestmove {move}')
                           else:
                                if DEBUG:
                                    logging.info("Place pieces on their places")
                                    output(f'info string place pieces on their places')


if __name__ == '__main__':
    main()

