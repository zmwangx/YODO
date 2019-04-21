#!/usr/bin/env python3

import json
import mimetypes
import os
import pathlib
import shutil
import string
import tempfile
import urllib.parse
import uuid

import flask
from werkzeug.middleware.proxy_fix import ProxyFix


app = flask.Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", default=0)) or 10 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

if not os.getenv("STATE_DIRECTORY"):
    raise RuntimeError("STATE_DIRECTORY not set or empty")
STATE_DIR = pathlib.Path(os.getenv("STATE_DIRECTORY"))
if not STATE_DIR.is_dir():
    raise RuntimeError(
        f"STATE_DIRECTORY {str(STATE_DIR)!r} does not exist or is not a directory"
    )
if not STATE_DIR.is_absolute():
    raise RuntimeError(f"STATE_DIRECTORY {str(STATE_DIR)!r} is not an absolute path")


def url_for(endpoint, *args, **kwargs):
    return flask.url_for(endpoint, *args, **kwargs, _external=True)


def usage_instructions():
    return f"""\
YODO - You Only Download Once
=============================

YODO is an ephemeral file hosting service.

There are two ways to upload a file (say, image.png):

    $ curl --header 'Content-Type: image/png' --data-binary @image.png {url_for('index')}
    $ curl --form 'file=@image.png;type=image/png' {url_for('index')}

Apparently these are just different flavors of POST requests. The former
simply uses the content of the file as request body, and identifies
itself via the Content-Type header, but there is no way to provide a
filename. The latter is a multipart/form-data request where the content
is uploaded through the 'file' part; both Content-Type and filename may
be specified this way. Note that application/x-www-form-urlencoded
requests are not allowed.

There is an upload size limit of {MAX_CONTENT_LENGTH} bytes.

The response should be HTTP 201 with the URL of the newly uploaded file,
e.g.,

    $ curl --dump-header - --form 'file=@image.png;type=image/png' {url_for('index')}
    HTTP/1.1 100 Continue

    HTTP/1.0 201 CREATED
    Content-Type: text/html; charset=utf-8
    Content-Length: 60

    {url_for('retrieval', identifier='2c8000bc-7c10-4700-9cc3-eb0dce0a9d1a')}

The URL is available for download exactly once; the file is destroyed
after the first GET request (but not HEAD). Content-Type, if not
specified at upload time, is guessed. The Content-Disposition header
is available if filename was specified at upload time.

    $ curl --head {url_for('retrieval', identifier='2c8000bc-7c10-4700-9cc3-eb0dce0a9d1a')}
    HTTP/1.0 200 OK
    Content-Type: image/png
    Content-Disposition: attachment; filename="image.png"
    Content-Length: 25715
"""


def bad_request(msg, code=400):
    return msg, code, {"Content-Type": "text/plain"}


def server_error(msg, code=500):
    return msg, code, {"Content-Type": "text/plain"}


def content_disposition_header(filename):
    # Is this filename safe for legacy quoted-string filename parameter?
    if all(ch in string.printable and ch not in '\\"' for ch in filename):
        return f'attachment; filename="{filename}"'
    else:
        # RFC 5987/8187 filename* parameter. Not universally supported.
        # Typical browsers and wget with --content-disposition supports
        # it, but curl (at least up to 7.64.1) with --remote-header-name
        # does not.
        return f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"


def exclusive_create(path):
    os.close(os.open(path, os.O_CREAT | os.O_EXCL))


def try_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


@app.route("/", methods=["GET", "POST"])
def index():
    if flask.request.method in ["GET", "HEAD"]:
        return usage_instructions(), {"Content-Type": "text/plain"}
    elif flask.request.method == "POST":
        if flask.request.content_type == "application/x-www-form-urlencoded":
            return bad_request("application/x-www-form-urlencoded not allowed.\n")

        stream = None
        content_type = None
        filename = None

        if not flask.request.files:
            stream = flask.request.stream
            content_type = flask.request.content_type
        else:
            if "file" not in flask.request.files:
                return bad_request("No file part.\n")
            file = flask.request.files["file"]
            stream = file.stream
            content_type = file.content_type
            filename = file.filename

        if not content_type and filename:
            content_type, _ = mimetypes.guess_type(filename, strict=False)

        with tempfile.NamedTemporaryFile(dir=STATE_DIR, delete=False) as tmp:
            try:
                shutil.copyfileobj(stream, tmp)
                stream.close()
                tmp.close()
                for _ in range(3):
                    identifier = str(uuid.uuid4())
                    dest = STATE_DIR / identifier
                    try:
                        exclusive_create(dest)
                        os.rename(tmp.name, dest)
                    except OSError:
                        continue
                    metafile = STATE_DIR / f"{identifier}.json"
                    with metafile.open("w") as fp:
                        json.dump(
                            dict(content_type=content_type, filename=filename), fp
                        )
                    return f"{url_for('retrieval', identifier=identifier)}\n", 201
                # Either the filesystem is broken and open(2) or
                # rename(2) stops working, or you hit the jackpot with
                # 3 UUID collisions in a row.
                return server_error("Failed to allocate URL.")
            finally:
                try_unlink(tmp.name)
    else:
        raise NotImplementedError


@app.route("/<uuid:identifier>")
def retrieval(identifier):
    identifier = str(identifier)
    file = STATE_DIR / identifier
    metafile = STATE_DIR / f"{identifier}.json"
    lockfile = STATE_DIR / f"{identifier}.lock"

    def generate_response():
        with metafile.open() as fp:
            metadata = json.load(fp)
        content_type = metadata["content_type"] or "application/octet-stream"
        filename = metadata["filename"]

        headers = {"Content-Type": content_type}
        if filename:
            headers["Content-Disposition"] = content_disposition_header(filename)

        with file.open("rb") as fp:
            body = fp.read()

        return body, headers

    if flask.request.method == "HEAD":
        try:
            return generate_response()
        except OSError:
            flask.abort(404)

    try:
        exclusive_create(lockfile)
    except:
        # Beaten to it by another request.
        flask.abort(404)
    try:
        return generate_response()
    except OSError:
        flask.abort(404)
    finally:
        try_unlink(file)
        try_unlink(metafile)
        try_unlink(lockfile)


def main():
    app.run(host="127.0.0.1", port=14641, debug=True, threaded=True)


if __name__ == "__main__":
    main()
