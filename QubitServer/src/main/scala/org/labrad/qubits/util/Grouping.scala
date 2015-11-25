package org.labrad.qubits.util

import scala.collection.mutable

/**
 * Utility methods for common grouping operations on collections.
 *
 * Standard scala collections have a `groupBy` method which takes a function
 * that computes a key for each element of the collection, and produces a map
 * from the computed key to a sequence of values:
 *
 * def groupBy[K](keyFunc: A => K): Map[K, Seq[A]]
 *
 * A case that arises commonly is when the collection elements themselves are
 * tuples of type (K, V) and we wish to group by the first element. If we use
 * the standard groupBy for this, the resulting values include the full tuples
 * Seq[(K, V)] where we typically want just Seq[V], so we have to do further
 * processing after the groupBy. The `groupByKeyValue` method added here does
 * this in one step.
 *
 * Another case is when we wish to do a grouping where we compute a key K for
 * each element of the collection, and also a value V to be retained in the
 * grouping. In this case, we supply a function not from A => K, but rather
 * from A => (K, V), and then treat the resulting tuples as described above.
 * The `groupByComputedKeyValue` method added here does this.
 *
 * To make these methods available on collections, just import the contents
 * of the Grouping object, e.g.:
 *
 * import org.labrad.qubits.util.Grouping._
 */
object Grouping {

  /**
   * Group an iterable collection of tuples into a map indexed by the first
   * element, keeping values from the second element.
   */
  implicit class GroupableByKeyValue[K, V](val collection: Iterable[(K, V)]) extends AnyVal {
    def groupByKeyValue: Map[K, Seq[V]] = {
      collection.groupByComputedKeyValue(identity)
    }
  }

  /**
   * Group elements of a collection based on a key and value computed
   * for each element.
   */
  implicit class GroupableByComputedKeyValue[A](val collection: Iterable[A]) extends AnyVal {
    def groupByComputedKeyValue[K, V](keyValueFunc: A => (K, V)): Map[K, Seq[V]] = {
      val map = mutable.Map.empty[K, mutable.Buffer[V]]
      for (item <- collection) {
        val (key, value) = keyValueFunc(item)
        val values = map.getOrElseUpdate(key, mutable.Buffer.empty[V])
        values += value
      }
      map.mapValues(_.toVector).toMap
    }
  }

}
