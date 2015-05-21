package org.labrad.qubits.util

import org.labrad.data.Data

/**
 * A utility class that encapsulates an array of complex numbers.
 * 
 * This class is much more efficient than having an array of Complex objects
 * because only two arrays need to be allocated, not one object per element
 * in the array.  In addition, this class has convenience methods for converting
 * to and from LabRAD data.
 */
case class ComplexArray(re: Array[Double], im: Array[Double]) {

  require(re.length == im.length, "real and imaginary arrays must have the same length")
  val length = re.length

  /**
   * Convert a complex array into LabRAD data of type *c
   */
  def toData(): Data = {
    val iq = Data.ofType("*c")
    iq.setArraySize(re.length)
    for (i <- 0 until length) {
      iq.setComplex(re(i), im(i), i)
    }
    iq
  }
}

object ComplexArray {
  /**
   * Create a complex array from LabRAD data of type *c
   * @param vals
   * @return
   */
  def fromData(vals: Data): ComplexArray = {
    val len = vals.getArraySize()
    val re = Array.ofDim[Double](len)
    val im = Array.ofDim[Double](len)
    for (i <- 0 until len) {
      val c = vals.get(i).getComplex()
      re(i) = c.getReal()
      im(i) = c.getImag()
    }
    ComplexArray(re, im)
  }
}
