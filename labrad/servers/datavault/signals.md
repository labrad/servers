# Data Vault signals for asynchronous updates

The Data Vault server uses labrad messages to send asynchronous updates about
various events to interested clients. For each message type, there is a
corresponding setting that can be used by clients to tell the server that they
want to start or stop receiving those messages. This combination of a message
and a setting to register interest in that message is referred to as a "Signal",
and uses the pylabrad machinery from `labrad.server.Signal` for implementation.

To connect to a signal, the client makes a request to the registration method
in a particular context, passing a message id. After the client connects,
whenever the server emits that signal it will send a message to the client
in the same context it used when connecting, and with the message ID set to the
ID the client used when connecting. It is possible for a single client to
connect to a given signal in multiple contexts, for example to get messages
about additions to multiple data sets that it has opened in different contexts;
however, a client can only register one listener per context.

The signals defined by the Data Vault can be divided into two categories: those
that send messages related to the current directory, and those that send
messages related to the currently-opened dataset. In both cases, we care about
the current directory or dataset in the context that was used when connecting
to the signal.

Signals related to the current directory are as follows:

* `signal: new dir`: when a new subdirectory is created, sends a string (`s`) with the directory name
* `signal: new dataset`: when a new dataset is created, sends a string (`s`) with the dataset name
* `signal: tags updated`: when tags are changed on datasets or directories, sends the new tags `*(s*s){dir tags}, *(s*s){dataset tags}`

Signals related to the currently-open dataset are as follows:

* `signal: data available`: when data is added to the dataset, send an empty message to clients.
* `signal: new parameter`: when a parameter is added to the dataset, send an empty message to clients.
* `signal: comments available`: when a comment is added to the dataset, send an empty message to clients.

These dataset-specific signals function slightly differently than other signals,
because the server keeps track of whether it has sent a message to connected
listeners and whether they have subsequently fetched more data, parameters, or
comments. When an event occurs that could trigger one of these messages, the
server will send at most one message to a listener in a given context, until
the client requests the new data in that context. For example, if a client
connects to the `data available` signal, then when the next chunk of data is
added to the dataset the client will be sent a message. If more chunks are
added, however, the server will not send any additional messages until the
client calls `get` to load more data. Another way to say this is the server
will send at most one `data available` message between successive calls to `get`
in a given context. The other signals work similarly; the server sends at most
one `comments available` message between subsequent calls to `get_comments` in
a given context, and at most one `new parameter` message in between subsequent
calls to `parameters` or `get_parameters` in a given context.
