package org.labrad.qubits.util

import org.labrad.data._

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
    val iq = Data("*c")
    iq.setArraySize(re.length)
    val it = iq.flatIterator
    for (i <- 0 until length) {
      it.next.setComplex(re(i), im(i))
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
    val len = vals.arraySize
    val re = Array.ofDim[Double](len)
    val im = Array.ofDim[Double](len)
    val it = vals.flatIterator
    for (i <- 0 until len) {
      val c = it.next
      re(i) = c.getReal
      im(i) = c.getImag
    }
    ComplexArray(re, im)
  }
}
