package org.labrad.ethernet.server

import scala.collection.mutable
import scala.concurrent.{Await, Future, Promise}
import scala.concurrent.duration._

class Awaitable {

  private val lock = new Object
  private val waiters = mutable.Buffer.empty[(() => Boolean, Promise[Unit])]

  /**
   * Wait for the specified condition to become true. Returns a Duration
   * indicating how much time elapsed while waiting, which may be zero if the
   * condition was true initially. If the time elapses before the condition
   * becomes true, raises an exception.
   */
  def await(timeout: Duration)(cond: => Boolean): Duration = {
    val futureOpt = lock.synchronized {
      if (cond) {
        None
      } else {
        val promise = Promise[Unit]
        waiters += (() => cond, promise)
        Some(promise.future)
      }
    }
    futureOpt match {
      case None => 0.seconds
      case Some(f) =>
        val start = System.nanoTime
        Await.result(f, timeout)
        val elapsed = System.nanoTime - start
        elapsed.nanoseconds
    }
  }

  /**
   * Perform the given action which may update internal state and then trigger
   * any waiters whose conditions may have changed as a result.
   */
  def update[A](f: => A): A = {
    lock.synchronized {
      val result = f
      val removals = Seq.newBuilder[Int]
      for (((cond, promise), i) <- waiters.zipWithIndex) {
        if (cond()) {
          promise.success()
          removals += i
        }
      }
      for (i <- removals.result.reverse) {
        waiters.remove(i)
      }
      result
    }
  }

  /**
   * Perform the given action and return the result, without notifying waiters.
   * This should be used for any operations that modify internal state which is
   * also accessed by await conditions or update.
   */
  def sync[A](f: => A): A = {
    lock.synchronized {
      f
    }
  }

  /**
   * Fail all waiters with the given throwable as the cause of failure.
   */
  def failAll[A](cause: Throwable)(f: => A): A = {
    lock.synchronized {
      val result = f
      for ((_, promise) <- waiters) {
        promise.failure(cause)
      }
      waiters.clear()
      result
    }
  }
}

/**
 * A queue that buffers packets and allows to wait until a given number of
 * packets accumulate in the queue.
 */
class PacketQueue[A] {

  private val awaitable = new Awaitable
  private val packets = mutable.Buffer.empty[A]

  /**
   * Wait for the specified number of packets to accumulate in the queue.
   */
  def await(n: Long, timeout: Duration): Unit = {
    require(n >= 0, s"number of packets to await must be non-negative. got $n")
    awaitable.await(timeout) {
      packets.size >= n
    }
  }

  /**
   * Enqueue a packet, updating waiters who may now be able to proceed.
   */
  def enqueue(packet: A): Unit = {
    awaitable.update {
      packets += packet
    }
  }

  /**
   * Take the specified number of packets from the buffer.
   * Raises an exception if there are not enough packets buffered.
   */
  def take(n: Int): Seq[A] = {
    awaitable.sync {
      if (packets.size < n) {
        sys.error(s"not enough packets in buffer")
      }
      val result = packets.take(n).toSeq
      packets.remove(0, n)
      result
    }
  }

  /**
   * Drop the specified number of packets from the buffer.
   * Raises an exception if there are not enough packets buffered.
   */
  def drop(n: Int): Unit = {
    awaitable.sync {
      if (packets.size < n) {
        sys.error(s"not enough packets in buffer")
      }
      packets.remove(0, n)
    }
  }

  /**
   * Reset the trigger count and fail any outstanding promises.
   */
  def clear(reason: Throwable = new Exception("packet queue cleared")): Unit = {
    awaitable.failAll(reason) { packets.clear() }
  }
}
