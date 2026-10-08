using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.Audio;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace SeedArsenal
{
	// Chat commands (type them in chat, like /help). CommandType.Chat runs on the typing player's own
	// machine, in single player and on a multiplayer client.

	/// <summary>/arsenal: one of every item this mod adds.</summary>
	public class ArsenalCommand : ModCommand
	{
		public override CommandType Type => CommandType.Chat;
		public override string Command => "arsenal";
		public override string Description => "Gives you every Seed Arsenal weapon";

		public override void Action(CommandCaller caller, string input, string[] args)
		{
			var source = new EntitySource_DebugCommand("/" + Command);
			var names = new List<string>();
			foreach (var item in Mod.GetContent<ModItem>())
			{
				caller.Player.QuickSpawnItem(source, item.Type); // dropped on the player, picked up at once (synced in multiplayer)
				names.Add(item.DisplayName.Value);
			}
			caller.Reply("Seed Arsenal: " + string.Join(", ", names), new Color(255, 170, 60));
		}
	}

	/// <summary>/mothership: summons the Drone Mothership near you.</summary>
	public class MothershipCommand : ModCommand
	{
		public override CommandType Type => CommandType.Chat;
		public override string Command => "mothership";
		public override string Description => "Summons the Drone Mothership boss";

		public override void Action(CommandCaller caller, string input, string[] args)
		{
			var player = caller.Player;
			int type = ModContent.NPCType<DroneMothership>();
			if (NPC.AnyNPCs(type))
			{
				caller.Reply("The Drone Mothership is already here.", new Color(255, 170, 60));
				return;
			}
			SoundEngine.PlaySound(SoundID.Roar, player.position);
			// the vanilla boss-summon path: SpawnOnPlayer places it just off-screen and announces it;
			// a multiplayer client asks the server instead (allowed by NPCID.Sets.MPAllowedEnemies)
			if (Main.netMode != NetmodeID.MultiplayerClient)
				NPC.SpawnOnPlayer(player.whoAmI, type);
			else
				NetMessage.SendData(MessageID.SpawnBossUseLicenseStartEvent, number: player.whoAmI, number2: type);
		}
	}
}
