package org.labrad.ethernet.server

import scala.concurrent.duration._

/**
 * A counter that keeps track of received triggers and allows clients
 * to wait for a certain number of triggers to be received (even if those
 * triggers were received before the call to await).
 */
class TriggerCounter {

  private val awaitable = new Awaitable
  private var triggers = 0L

  /**
   * Await the specified number of triggers.
   */
  def await(numTriggers: Long, timeout: Duration): Duration = {
    require(numTriggers >= 0, s"number of triggers must be non-negative. got $numTriggers")
    awaitable.sync { triggers -= numTriggers }
    awaitable.await(timeout) { triggers >= 0 }
  }

  /**
   * Send a trigger to the counter and update waiters.
   */
  def trigger(): Unit = {
    awaitable.update { triggers += 1 }
  }

  /**
   * Reset the trigger count and fail any outstanding waiters.
   */
  def clear(reason: Throwable = new Exception("triggers cleared")): Unit = {
    awaitable.failAll(reason) { triggers = 0 }
  }
}
