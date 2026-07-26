using System.Collections.Generic;

namespace Microsoft.Xna.Framework.Net
{
    public class AvailableNetworkSessionCollection
        : List<AvailableNetworkSession>
    {

    }


    public class AvailableNetworkSession
    {
        public int CurrentGamerCount { get; set; }

        public int OpenPublicGamerSlots { get; set; }

        public string HostGamertag { get; set; }
    }
}