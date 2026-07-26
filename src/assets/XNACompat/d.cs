using System.IO;

namespace Microsoft.Xna.Framework.Net
{
    public class PacketReader
    {
        private readonly BinaryReader reader;


        public PacketReader(byte[] data)
        {
            reader = new BinaryReader(
                new MemoryStream(data)
            );
        }


        public byte ReadByte()
            => reader.ReadByte();


        public int ReadInt32()
            => reader.ReadInt32();


        public short ReadInt16()
            => reader.ReadInt16();


        public long ReadInt64()
            => reader.ReadInt64();


        public float ReadSingle()
            => reader.ReadSingle();


        public double ReadDouble()
            => reader.ReadDouble();


        public bool ReadBoolean()
            => reader.ReadBoolean();


        public string ReadString()
            => reader.ReadString();


        public byte[] ReadBytes(int count)
            => reader.ReadBytes(count);
    }
}