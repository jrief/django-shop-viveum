Unfortunately, Viveum is using a configuration in its SSL server, which can cause
problems with openssl. In case, while running unit tests, you get an error such as::

    SSLError: [Errno 8] _ssl.c:504: EOF occurred in violation of protocol

please read this post: http://stackoverflow.com/questions/14102416/python-requests-requests-exceptions-sslerror-errno-8-ssl-c504-eof-occurred
Edit the file ``<your-python-lib>/site-packages/requests/packages/urllib3/connectionpool.py``, 
find the call to ``self.sock = ssl_wrap_socket(sock, self.key_file, self.cert_file, ...)``
and change argument from ``ssl_version=resolved_ssl_version`` to ``ssl_version=ssl.PROTOCOL_TLSv1``.
