import asyncio


class MyQueue(asyncio.Queue):
    """Custom async queue implementation that handles clearing the underlying queue.
    Breaks support for task_done() and join().
    """

    def trigger_shutdown(self):
        """Trigger a shutdown of queue consumers"""
        self.clear_and_put(None)

    def put_many(self, *args):
        """Put elements given in args on the queue"""
        assert len(args) >= 1, "must pass at least one arg"
        # Put all but the last item in
        for item in args[:-1]:
            self._put(item)
        # Put the last item in and handle notifications
        self.put_nowait(args[-1])

    def clear_and_put(self, *args):
        """Clear the queue of all elements and replace with elements in args"""
        assert len(args) >= 1, "must pass at least one arg"
        self._queue.clear()
        self.put_many(*args)
