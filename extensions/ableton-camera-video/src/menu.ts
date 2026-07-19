import {
  ARRANGEMENT_SELECTION_SCOPES,
  CLIP_CONTEXT_SCOPES,
} from "./placement.js";

export const COMMAND_PLACE_VIDEO = "abletonCamera.placeVideoBelow";
export const COMMAND_PLACE_ALL_VIDEOS = "abletonCamera.placeAllVideosBelow";

type MenuContext = {
  ui: {
    registerContextMenuAction(
      scope: string,
      title: string,
      commandId: string,
    ): Promise<() => Promise<void>>;
  };
};

type Logger = {
  log(message: string): void;
};

export async function registerContextMenuActions(
  context: MenuContext,
  logger: Logger = console,
): Promise<void> {
  const actions = [
    ...CLIP_CONTEXT_SCOPES.map((scope) => ({
      commandId: COMMAND_PLACE_VIDEO,
      scope,
      title: "Place Camera Video Below",
    })),
    ...ARRANGEMENT_SELECTION_SCOPES.map((scope) => ({
      commandId: COMMAND_PLACE_ALL_VIDEOS,
      scope,
      title: "Place All Camera Videos Below",
    })),
  ];

  await Promise.all(
    actions.map(async ({ commandId, scope, title }) => {
      await context.ui.registerContextMenuAction(scope, title, commandId);
      logger.log(`Ableton Camera Video registered context menu action: ${scope}`);
    }),
  );
  logger.log(`Ableton Camera Video registered ${actions.length} context menu actions.`);
}
