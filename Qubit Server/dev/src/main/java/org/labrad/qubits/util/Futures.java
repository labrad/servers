package org.labrad.qubits.util;

import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import com.google.common.base.Function;
import com.google.common.collect.Lists;

public class Futures {
  /**
   * Create from an existing Future a new Future that transforms the result using the given function.
   * @param <F>
   * @param <T>
   * @param in
   * @param func
   * @return
   */
  public static <F, T> Future<T> chain(final Future<F> in, final Function<F, T> func) {
    return new Future<T>() {
      @Override
      public boolean cancel(boolean mayInterruptIfRunning) {
        return in.cancel(mayInterruptIfRunning);
      }

      @Override
      public T get() throws InterruptedException, ExecutionException {
        return func.apply(in.get());
      }

      @Override
      public T get(long timeout, TimeUnit unit)
          throws InterruptedException, ExecutionException, TimeoutException {
        return func.apply(in.get(timeout, unit));
      }

      @Override
      public boolean isCancelled() {
        return in.isCancelled();
      }

      @Override
      public boolean isDone() {
        return in.isDone();
      }

    };
  }

  /**
   * Create from an existing list of Futures a new Future that combines the results using the given function.
   * @param <F>
   * @param <T>
   * @param futures
   * @param func
   * @return
   */
  public static <F, T> Future<T> chainAll(final List<Future<F>> futures, final Function<List<F>, T> func) {
    return new Future<T>() {
      @Override
      public boolean cancel(boolean mayInterruptIfRunning) {
        boolean cancelled = true;
        for (Future<F> f : futures) {
          cancelled &= f.cancel(mayInterruptIfRunning);
        }
        return cancelled;
      }

      @Override
      public T get() throws InterruptedException, ExecutionException {
        List<F> results = Lists.newArrayList();
        for (Future<F> f : futures) {
          results.add(f.get());
        }
        return func.apply(results);
      }

      @Override
      public T get(long timeout, TimeUnit unit)
          throws InterruptedException, ExecutionException, TimeoutException {
        List<F> results = Lists.newArrayList();
        for (Future<F> f : futures) {
          results.add(f.get(timeout, unit));
        }
        return func.apply(results);
      }

      @Override
      public boolean isCancelled() {
        boolean isCancelled = true;
        for (Future<F> f : futures) {
          isCancelled &= f.isCancelled();
        }
        return isCancelled;
      }

      @Override
      public boolean isDone() {
        boolean isDone = true;
        for (Future<F> f : futures) {
          isDone &= f.isDone();
        }
        return isDone;
      }

    };
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
  public static <F> Future<Void> waitForAll(final List<Future<F>> futures) {
    return chainAll(futures, new Function<List<F>, Void>() {
      @Override
      public Void apply(List<F> results) {
        return null;
      }
    });
  }
}
