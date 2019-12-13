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
import threading
import queue

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

stack = queue.Queue()

interrupted = threading.Lock()
interrupted.acquire()

class ucireader(threading.Thread):
    def __init__ (self, device='sys.stdin'):
        threading.Thread.__init__(self)
        self.device = device

    def run(self):
        while not interrupted.acquire(blocking=False):
            try:
                line = input()
                stack.put(line)
            except EOFError:
                # we quit
                stack.put('quit')
                pass

inputthread = ucireader('sys.stdin')
inputthread.start()

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
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    sock.bind(LISTEN_SOCKET)
    sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
    recv_list = [sock]
    new_usb_data = False
    usb_data_exist = False

    def send_leds(message=b'\x00' * 8):
        sock.sendto(message, SEND_SOCKET)

    send_leds(b'\xff' * 8)
    chessboard = chess.Board()
    board_state = chessboard.fen()
    move = []
    starting_position = chess.STARTING_FEN
    rotate180 = False
    mystate = "init"


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

    send_leds()

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

        if not stack.empty():
            smove = stack.get()
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
                logging.debug(f'unandled: {smove}')
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
                                    board1 = chess.BaseBoard(s1)
                                    board2 = chess.BaseBoard(s2)
                                    for x in range(chess.A1, chess.H8+1):
                                        if board1.piece_at(x) != board2.piece_at(x):
                                            logging.debug(f'Difference on Square {chess.SQUARE_NAMES[x]} - {board1.piece_at(x)} <-> {board2.piece_at(x)}')
                                    if move_detect_tries > move_detect_max_tries:
                                        logging.info("Invalid move")
                                    else:
                                        move_detect_tries = 0
                                if move:
                                   # highlight right LED
                                    i, value, i_source, value_source = codes.move2led(
                                        move, rotate180
                                    )  # error here if checkmate before
                                    message = bytearray()
                                    for j in range(8):
                                        if j != i and j != i_source:
                                            message.append(0)
                                        elif j == i and j == i_source:
                                            message.append(value + value_source)
                                        elif j == i:
                                            message.append(value)
                                        else:
                                            message.append(value_source)

                                    send_leds(message)
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
                                    board1 = chess.BaseBoard(s1)
                                    board2 = chess.BaseBoard(s2)
                                    for x in range(chess.A1, chess.H8+1):
                                        if board1.piece_at(x) != board2.piece_at(x):
                                            logging.debug(f'Difference on Square {chess.SQUARE_NAMES[x]} - {board1.piece_at(x)} <-> {board2.piece_at(x)}')

                                    if move_detect_tries > move_detect_max_tries:
                                        logging.info("Invalid move")
                                    else:
                                        move_detect_tries = 0


                            else:
                                if DEBUG:
                                    logging.info("Place pieces on their places")
                                    output(f'info string place pieces on their places')
                                    logging.info("Virtual board: %s", chessboard.fen())
                        else: # board is the same
                            if mystate == "user_shall_place_oppt_move":
                                logging.info("user has moved opponent, now it's his own turn")
                                mystate = "user_shall_place_his_move" 
                            send_leds()

    # we quite, stop input thread
    interrupted.release()

if __name__ == '__main__':
    main()

