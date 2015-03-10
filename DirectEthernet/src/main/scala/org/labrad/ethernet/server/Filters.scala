package org.labrad.ethernet.server

import org.pcap4j.packet.EthernetPacket
import org.pcap4j.packet.namednumber.EtherType
import org.pcap4j.util.MacAddress

trait Filter {
  def apply(pkt: EthernetPacket): Boolean
}

object Filters {
  type FilterFunc = EthernetPacket => Boolean

  abstract class Require(f: FilterFunc) extends Filter {
    def apply(pkt: EthernetPacket): Boolean = f(pkt)
  }
  abstract class Reject(f: FilterFunc) extends Filter {
    def apply(pkt: EthernetPacket): Boolean = !f(pkt)
  }

  def srcMac(addr: MacAddress): FilterFunc = _.getHeader.getSrcAddr == addr
  case class RequireSrcMac(addr: MacAddress) extends Require(srcMac(addr))
  case class RejectSrcMac(addr: MacAddress) extends Reject(srcMac(addr))

  def dstMac(addr: MacAddress): FilterFunc = _.getHeader.getDstAddr == addr
  case class RequireDstMac(addr: MacAddress) extends Require(dstMac(addr))
  case class RejectDstMac(addr: MacAddress) extends Reject(dstMac(addr))

  def length(len: Int): FilterFunc = _.getPayload.getRawData.length == len
  case class RequireLength(len: Int) extends Require(length(len))
  case class RejectLength(len: Int) extends Reject(length(len))

  def etherType(typ: EtherType): FilterFunc = _.getHeader.getType == typ
  case class RequireEtherType(typ: EtherType) extends Require(etherType(typ))
  case class RejectEtherType(typ: EtherType) extends Reject(etherType(typ))

  val rawEtherType: FilterFunc = { pkt =>
    val typ = pkt.getHeader.getType
    val len = pkt.getPayload.getRawData.length
    typ == EtherType.getInstance(len.toShort)
  }
  case object RequireRawEtherType extends Require(rawEtherType)
  case object RejectRawEtherType extends Reject(rawEtherType)

  def content(offset: Int, pattern: Seq[Byte]): FilterFunc = { pkt =>
    val data = pkt.getPayload.getRawData
    if (data.length < offset + pattern.length) {
      false
    } else {
      (0 until pattern.length).forall { i =>
        data(offset + i) == pattern(i)
      }
    }
  }
  case class RequireContent(offset: Int, pattern: Seq[Byte]) extends Require(content(offset, pattern))
  case class RejectContent(offset: Int, pattern: Seq[Byte]) extends Reject(content(offset, pattern))
}
