from __future__ import print_function
import serial.tools.list_ports
DEBUG = False

# for exe compile run python 1.py py2exe
import argparse
import datetime
import time
from select import *
from socket import *
from utils import port2udp, port2number

print("--- usbtool started ---")

parser = argparse.ArgumentParser()
parser.add_argument('--port')
args = parser.parse_args()
if args.port:
    print('Got port argument', args.port)
else:
    print('No port argument speicified')

board_listen_port, gui_listen_port = port2udp(port2number(args.port))
print('USBTOOL: Board listen port: %s, gui listen port: %s' % (board_listen_port, gui_listen_port))
uart_ok = False
try:
    uart = serial.Serial(args.port, 38400, timeout=2.5)  # 0-COM1, 1-COM2 / speed /
    uart_ok = True
except:
    print("can't open Serial port")

if not uart_ok:
    try:
        uart = serial.Serial(args.port, 38400, timeout=2.5)  # 0-COM1, 1-COM2 / speed /
        uart_ok = True
    except:
        print("can't open Serial")
        exit(1)

# time.sleep(3) # without it, .write not work


# erase RS buf
if uart_ok:
    uart.flushInput()

print("Started usbtool. waiting for new messages")

timeout_RS = datetime.datetime.now()
counter = 0
message = ""

k = 0

SEND_SOCKET = ("127.0.0.1", gui_listen_port)  # send to
LISTEN_SOCKET = ("127.0.0.1", board_listen_port)  # listen to
sock = socket(AF_INET, SOCK_DGRAM)
sock.bind(LISTEN_SOCKET)
sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
recv_list = [sock]
# sock.sendto( message, KUDA_POSYLAT )
# sock.close()


while 1:
    recv_ready, wtp, xtp = select(recv_list, [], [], 0.001)

    if recv_ready:
        try:
            data, addr = sock.recvfrom(2048)
            if DEBUG:
                print("sending to usb data with length =", len(data))
            uart.write(data)
        except:
            print("chess main part not running")

    if not uart_ok:
        try:
            uart = serial.Serial(
                args.port, 38400, timeout=2.5
            )  # 0-COM1, 1-COM2 / speed /
            uart_ok = True
        except:
            print("can't open Serial at ", args.port)

    time.sleep(0.001)
    t = datetime.datetime.now()

    # print 2
    # if t>timeout_RS:
    # RS-485 lost connection

    ############################################################################
    # UART processing
    if uart_ok:

        timeout_RS = t + datetime.timedelta(seconds=48)

        to_read = 0
        try:
            to_read = uart.inWaiting()
        except:
            print("uart.inWaiting failed")

        if to_read > 0:
            # print counter
            while uart.inWaiting():
                # try:
                #    byte = ord( uart.read() )
                try:
                    c = uart.read()
                    counter += 1
                    got_byte = True
                except:
                    print("Cannot do uart.read()")
                    uart_ok = False
                    got_byte = False

                if got_byte and c == "\n":
                    uart.flushInput()
                    k += 1
                    if DEBUG:
                        print(k)
                    # print counter
                    message = message[1 : len(message) - 2]
                    # print [message]
                    if DEBUG:
                        print(len(message.split(" ")), "numbers")
                    if len(message.split(" ")) == 320:  # 64*5
                        try:
                            #                        KUDA_POSYLAT = ('127.0.0.1', 3003) # send to
                            #                        NASH_ADRES =   ('127.0.0.1', 3002) # listen to
                            #                        sock = socket(AF_INET, SOCK_DGRAM)
                            #                        sock.bind( NASH_ADRES )
                            #                        sock.setsockopt( SOL_SOCKET,SO_BROADCAST, 1 )
                            sock.sendto(message, SEND_SOCKET)
                        #                        sock.close()
                        except:
                            print("can't send UDP")
                    counter = 0
                    message = ""
                else:
                    message += c
