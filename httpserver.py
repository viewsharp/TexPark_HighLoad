import os, socket, select
from signal import SIGTERM
from socket import socket
from datetime import datetime
from http.client import responses
from urllib.parse import unquote

WORKER_COUNT = 4

HTTP_VERSION = '1.1'
HTTP_SERVER_NAME = 'HttpServer'
HTTP_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
FILE_CONTENT_TYPES = {
    'html': 'text/html',
    'css': 'text/css',
    'js': 'application/javascript',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'swf': 'application/x-shockwave-flash'
}
ROOT_PATH = os.path.realpath('./')


def read_chunks(file_path, chunk_size=1024):
    with open(file_path, 'rb') as f:
        data = f.read(chunk_size)
        while data:
            yield data
            data = f.read(chunk_size)


def log(level, *args):
    print(datetime.utcnow().strftime(HTTP_DATE_FORMAT), '[{}]'.format(level), *args)


class Server:
    def __init__(self, addr, port):
        self.addr = addr
        self.port = port
        self.__worker = None

    def start(self):
        with socket() as sock:
            sock.bind((self.addr, self.port))
            sock.listen()

            self.__worker = [Worker(sock) for _ in range(WORKER_COUNT)]

            for worker in self.__worker:
                worker.start()

            sock.close()

            for worker in self.__worker:
                worker.join()

    def stop(self):
        for worker in self.__worker:
            worker.terminate()
            worker.join()


class Client:
    def __init__(self, conn):
        self.__conn = conn
        self.__request = b''

    def write_request(self, data):
        self.__request += data



class Worker:
    def __init__(self, sock):
        """
        :type sock: socket
        """
        self.__socket = sock
        self.__pid = 0

    def start(self):
        pid = os.fork()

        if pid == 0:
            try:
                self._run()
            except KeyboardInterrupt:
                self._stop()
            except Exception as e:
                log('ERROR', e)

            exit()

        self.__pid = pid

    def join(self):
        if self.__pid == 0:
            raise Exception('worker not started')
        os.waitpid(self.__pid, 0)

    def terminate(self):
        os.kill(self.__pid, SIGTERM)

    def _run(self):
        # epoll = select.epoll()
        # epoll.register(self.__socket.fileno(), select.)
        #
        # try:
        #     clients = {}
        #
        #     while True:
        #         events = epoll.poll(1)
        #         for fileno, event in events:
        #             if fileno == self.__socket.fileno():
        #                 connection, address = self.__socket.accept()
        #                 connection.setblocking(0)
        #                 epoll.register(connection.fileno(), select.EPOLLIN)
        #                 clients[connection.fileno()] = Client(connection)
        #             elif event & select.EPOLLIN:
        #                 requests[fileno] += connections[fileno].recv(1024)
        #                 if EOL1 in requests[fileno] or EOL2 in requests[fileno]:
        #                     epoll.modify(fileno, select.EPOLLOUT)
        #                 print('-' * 40 + '\n' + requests[fileno].decode()[:-2])
        #             elif event & select.EPOLLOUT:
        #                 byteswritten = connections[fileno].send(responses[fileno])
        #                 responses[fileno] = responses[fileno][byteswritten:]
        #                 if len(responses[fileno]) == 0:
        #                     epoll.modify(fileno, 0)
        #                 connections[fileno].shutdown(socket.SHUT_RDWR)
        #             elif event & select.EPOLLHUP:
        #                 epoll.unregister(fileno)
        #                 connections[fileno].close()
        #                 del connections[fileno]
        # finally:
        #     epoll.unregister(serversocket.fileno())
        #     epoll.close()
        #     serversocket.close()




        while True:
            conn, addr = self.__socket.accept()
            with conn:
                try:
                    request = Request(conn)
                except IOError as err:
                    response = Response(conn)
                    response.write_header(status=400)
                    log('ERROR', 400, err)
                else:
                    response = Response(conn)
                    self._handler(request, response)
                    log('INFO', response.status(), request.path())

    def _stop(self):
        self.__socket.close()

    def _handler(self, request, response):
        """
        :type request: Request
        :type response: Response
        """
        path = os.path.join(ROOT_PATH, request.path()[1:])
        if '/../' in path:
            response.write_header(status=403)
            return

        if os.path.isdir(path):
            path = os.path.join(path, 'index.html')
            if not os.path.isfile(path):
                response.write_header(status=403)
                return

        elif not os.path.isfile(path):
            log('WARNING', 'path not exists:', path)

            response.write_header(status=404)
            return

        _, file_type = path.rsplit('.', 1)
        content_length = os.path.getsize(path)
        content_type = FILE_CONTENT_TYPES.get(file_type, '')

        response.write_header(content_type=content_type, content_length=content_length)

        if request.method() == 'HEAD':
            return

        response.write_file(path)


class Request:
    MAX_SIZE = 1024
    METHODS = {'GET', 'HEAD'}
    EOL1 = b'\n\n'
    EOL2 = b'\n\r\n'

    def __init__(self, conn):
        """
        :type conn: socket
        """
        request = b''
        while self.EOL1 not in request and self.EOL2 not in request:
            request += conn.recv(self.MAX_SIZE)

        request_text = request.decode('utf-8')
        log('INFO', repr(request_text))

        try:
            request_params = request_text.split(' ', 3)
            method, url, http_version = request_params[:3]
        except Exception:
            raise IOError('invalid request: parsing error')

        if method not in self.METHODS:
            raise IOError('invalid request: method error')
        self.__method = method

        self.__path = unquote(url).split('?')[0]

    def method(self):
        return self.__method

    def path(self):
        return self.__path


class Response:
    _SUCCESS_RESPONSE_TEMPLATE = '''\
HTTP/{http_ver} {status_code} {status_string}\r\n\
Server: {server_name}\r\n\
Date: {date}\r\n\
Connection: Close\r\n\
Content-Length: {content_length}\r\n\
Content-Type: {content_type}\r\n\r\n'''

    _FAIL_RESPONSE_TEMPLATE = '''\
HTTP/{http_ver} {status_code} {status_string}\r\n\
Server: {server_name}\r\n\
Date: {date}\r\n\
Connection: Closed\r\n\r\n'''

    _CONTENT_TYPES = {
        '',
        'text/html',
        'text/css',
        'application/javascript',
        'image/jpeg',
        'image/jpeg',
        'image/png',
        'image/gif',
        'application/x-shockwave-flash'
    }

    def __init__(self, connection):
        """
        :type connection: socket
        """
        self.__status = 200
        self.__connection = connection
        self.__content_length = 0
        self.__header_sent = False

    def write_header(self, status=200, content_length=0, content_type=''):
        self.__content_length = content_length
        self.__status = status

        if 200 <= status < 300:
            if content_type not in self._CONTENT_TYPES:
                raise ValueError('content type error')

            response_header = self._SUCCESS_RESPONSE_TEMPLATE.format(
                http_ver=HTTP_VERSION,
                status_code=status,
                status_string=responses[status],
                server_name=HTTP_SERVER_NAME,
                date=datetime.utcnow().strftime(HTTP_DATE_FORMAT),
                content_length=content_length,
                content_type=content_type
            ).encode()
        else:
            response_header = self._FAIL_RESPONSE_TEMPLATE.format(
                http_ver=HTTP_VERSION,
                status_code=status,
                status_string=responses[status],
                server_name=HTTP_SERVER_NAME,
                date=datetime.utcnow().strftime(HTTP_DATE_FORMAT),
            ).encode()

        self.__connection.sendall(response_header)
        self.__header_sent = True

    def write(self, data):
        """
        :type data: bytes
        """
        if not self.__header_sent:
            raise IOError('header not sent')

        self.__content_length -= len(data)
        if self.__content_length < 0:
            raise IOError('content length error')

        self.__connection.sendall(data)

    def write_file(self, path):
        with open(path, 'rb') as f:
            self.__connection.sendfile(f)

    def status(self):
        return self.__status


if __name__ == "__main__":
    server = Server("", 80)
    try:
        server.start()
    except KeyboardInterrupt:
        log('INFO', 'KeyboardInterrupt')
        server.stop()
    except Exception as e:
        log('ERROR', e)
