package org.labrad.qubits.util;

public class Failure {
  public static void fail(String errorMessage, Object... errorMessageArgs) {
    String message = String.format(errorMessage, errorMessageArgs);
    throw new RuntimeException(message);
  }

  public static void notImplemented() {
    throw new RuntimeException("Not implemented yet.");
  }
}
