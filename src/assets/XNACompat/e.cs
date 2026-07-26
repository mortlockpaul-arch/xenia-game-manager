using System.IO;

namespace Microsoft.Xna.Framework.Net
{
    public class PacketWriter
    {
        private readonly MemoryStream stream;
        private readonly BinaryWriter writer;


        public PacketWriter()
        {
            stream = new MemoryStream();
            writer = new BinaryWriter(stream);
        }


        public int Length => (int)stream.Length;


        public void Write(byte value)
            => writer.Write(value);

        public void Write(sbyte value)
            => writer.Write(value);

        public void Write(short value)
            => writer.Write(value);

        public void Write(ushort value)
            => writer.Write(value);

        public void Write(int value)
            => writer.Write(value);

        public void Write(uint value)
            => writer.Write(value);

        public void Write(long value)
            => writer.Write(value);

        public void Write(ulong value)
            => writer.Write(value);

        public void Write(float value)
            => writer.Write(value);

        public void Write(double value)
            => writer.Write(value);

        public void Write(bool value)
            => writer.Write(value);


        public void Write(string value)
        {
            writer.Write(value ?? "");
        }


        public void Write(byte[] value)
        {
            writer.Write(value);
        }


        public void Write(byte[] value, int offset, int count)
        {
            writer.Write(value, offset, count);
        }


        public byte[] ToArray()
        {
            writer.Flush();
            return stream.ToArray();
        }


        public void Clear()
        {
            stream.Position = 0;
            stream.SetLength(0);
        }
    }
}