package org.labrad.qubits.util

import java.util.List
import java.util.concurrent.ExecutionException
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import scala.collection.JavaConverters._

import com.google.common.base.Function
import com.google.common.collect.Lists

object Futures {
  /**
   * Create from an existing Future a new Future that transforms the result using the given function.
   * @param <F>
   * @param <T>
   * @param in
   * @param func
   * @return
   */
  def chain[F, T](in: Future[F], func: Function[F, T]): Future[T] = {
    new Future[T] {
      def cancel(mayInterruptIfRunning: Boolean): Boolean = {
        in.cancel(mayInterruptIfRunning)
      }

      @throws[InterruptedException]
      @throws[ExecutionException]
      def get(): T = {
        func.apply(in.get())
      }

      @throws[InterruptedException]
      @throws[ExecutionException]
      @throws[TimeoutException]
      def get(timeout: Long, unit: TimeUnit): T = {
        func.apply(in.get(timeout, unit))
      }

      def isCancelled(): Boolean = {
        in.isCancelled()
      }

      def isDone(): Boolean = {
        in.isDone()
      }
    }
  }

  /**
   * Create from an existing list of Futures a new Future that combines the results using the given function.
   * @param <F>
   * @param <T>
   * @param futures
   * @param func
   * @return
   */
  def chainAll[F, T](futures: List[Future[F]], func: Function[List[F], T]): Future[T] = {
    new Future[T] {
      def cancel(mayInterruptIfRunning: Boolean): Boolean = {
        var cancelled = true
        for (f <- futures.asScala) {
          cancelled &= f.cancel(mayInterruptIfRunning)
        }
        cancelled
      }

      @throws[InterruptedException]
      @throws[ExecutionException]
      def get(): T = {
        val results: List[F] = Lists.newArrayList()
        for (f <- futures.asScala) {
          results.add(f.get())
        }
        func.apply(results)
      }

      @throws[InterruptedException]
      @throws[ExecutionException]
      @throws[TimeoutException]
      def get(timeout: Long, unit: TimeUnit): T = {
        val results: List[F] = Lists.newArrayList()
        for (f <- futures.asScala) {
          results.add(f.get(timeout, unit))
        }
        func.apply(results)
      }

      def isCancelled(): Boolean = {
        var cancelled = true
        for (f <- futures.asScala) {
          cancelled &= f.isCancelled()
        }
        cancelled
      }

      def isDone(): Boolean = {
        var done = true
        for (f <- futures.asScala) {
          done &= f.isDone()
        }
        done
      }
    }
  }

  /**
   * Create from an existing list of Futures a new Future that waits for them all and discards the result.
   * @param <F>
   * @param <T>
   * @param futures
   * @param func
   * @return 
   * @return
   */
  def waitForAll[F](futures: List[Future[F]]): Future[Void] = {
    chainAll(futures, new Function[List[F], Void] {
      def apply(results: List[F]): Void = {
        null
      }
    })
  }
}
