namespace Microsoft.Xna.Framework.Net
{
    public class NetworkGamer
    {
        public string Gamertag { get; set; }

        public bool IsLocal { get; set; }

        public bool IsHost { get; set; }


        public virtual void SendData(
            PacketWriter writer)
        {
            // Offline compatibility stub
        }
    }


    public class LocalNetworkGamer : NetworkGamer
    {

    }
}