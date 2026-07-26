using System.Collections.Generic;

namespace Microsoft.Xna.Framework.Net
{
    public class NetworkSession
    {
        public List<NetworkGamer> Gamers
        {
            get;
        } = new();


        public NetworkGamer Host { get; set; }


        public bool IsDisposed { get; private set; }


        public static NetworkSession Create(
            NetworkSessionType type,
            int localGamers,
            int maxGamers)
        {
            var session = new NetworkSession();

            for (int i = 0; i < localGamers; i++)
            {
                session.Gamers.Add(
                    new LocalNetworkGamer
                    {
                        IsLocal = true
                    }
                );
            }

            return session;
        }


        public void Dispose()
        {
            IsDisposed = true;
        }


        public void Update()
        {
            // No Xbox networking
        }
    }


    public enum NetworkSessionType
    {
        SystemLink,
        PlayerMatch,
        Ranked
    }
}