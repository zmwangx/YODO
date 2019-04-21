# YODO - You Only Download Once

![Python 3.6, 3.7](https://img.shields.io/badge/python-3.6,%203.7-blue.svg?maxAge=86400)
![Powered by Flask](https://img.shields.io/badge/powered%20by-Flask-blue.svg?logo=flask&maxAge=86400)

YODO (pronounced *you&middot;dough*) is a dead simple, database-less ephemeral file hosting service powered by Flask.

You upload a file via a POST request; you receive a URL as response; you get to download the file via that URL, after which the file is destroyed. It's that simple.

**Security isn't a primary concern of this app. Don't host it on the public Internet!**

## Usage

Usage instructions (reproduced below) can be accessed at the root of the service via a GET request:

```console
$ ./app.py
* Serving Flask app "app" (lazy loading)
...
$ curl http://127.0.0.1:14641/
YODO - You Only Download Once
=============================

YODO is an ephemeral file hosting service.

There are two ways to upload a file (say, image.png):

    $ curl --header 'Content-Type: image/png' --data-binary @image.png http://127.0.0.1:14641/
    $ curl --form 'file=@image.png;type=image/png' http://127.0.0.1:14641/

Apparently these are just different flavors of POST requests. The former
simply uses the content of the file as request body, and identifies
itself via the Content-Type header, but there is no way to provide a
filename. The latter is a multipart/form-data request where the content
is uploaded through the 'file' part; both Content-Type and filename may
be specified this way. Note that application/x-www-form-urlencoded
requests are not allowed.

There is an upload size limit of 10485760 bytes.

The response should be HTTP 201 with the URL of the newly uploaded file,
e.g.,

    $ curl --dump-header - --form 'file=@image.png;type=image/png' http://127.0.0.1:14641/
    HTTP/1.1 100 Continue

    HTTP/1.0 201 CREATED
    Content-Type: text/html; charset=utf-8
    Content-Length: 60

    http://127.0.0.1:14641/2c8000bc-7c10-4700-9cc3-eb0dce0a9d1a

The URL is available for download exactly once; the file is destroyed
after the first GET request (but not HEAD). Content-Type, if not
specified at upload time, is guessed. The Content-Disposition header
is available if filename was specified at upload time.

    $ curl --head http://127.0.0.1:14641/2c8000bc-7c10-4700-9cc3-eb0dce0a9d1a
    HTTP/1.0 200 OK
    Content-Type: image/png
    Content-Disposition: attachment; filename="image.png"
    Content-Length: 25715
```

## Deployment

A sample gunicorn + systemd deployment setup is shown in [`etc/gunicorn-systemd.service`](etc/gunicorn-systemd.service).

Again, do NOT deploy this to a public facing network.

## Motivation

I have a Dockerized chat bot that only accepts HTTP URLs for images. I need to send real time, generated-on-the-fly tables/charts through it. The images become useless quickly so there's no point in archival (and I have all the historical data in a database anyway). While a dedicated, periodically wiped directory served by nginx would be enough, I figured that a service that cleans up after itself without cron intervention would be nicer. Hence this.

## License

Copyright (c) 2019 Zhiming Wang <i@zhimingwang.org>

This work is free. You can redistribute it and/or modify it under the
terms of the Do What The Fuck You Want To Public License, Version 2,
as published by Sam Hocevar.
