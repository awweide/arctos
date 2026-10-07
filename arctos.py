import random
import uuid


class DotMap(dict):
    """Small attribute-accessible mapping used for action payloads."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name, value):
        self[name] = value

    def copy(self):
        return type(self)(self)


class Action:
    """Base type and namespace for every action in the engine."""

    def __init__(self, engine, battle=None, parent=None, dotmap=None):
        self.id = str(uuid.uuid4())
        self.engine = engine
        self.battle = battle
        self.parent = parent
        self.list_children_queue = []
        self.list_children_done = []
        self.active_child = None
        self.step_function = self.resolve
        self.dotmap = dotmap if dotmap is not None else DotMap()
        self.resolved = False
        self.closed = False
        self.level = 0 if parent is None else parent.level + 1
        self.typename = type(self).__name__
        self.post_init()

    def step(self):
        """Advance this action by one engine step. Do not override."""
        self.step_function()

    def resolve(self):
        if not self.validate():
            print(f"{'  ' * self.level}{self.typename} invalid")
            self.step_function = self.close
            return

        self.engine.broadcast(self, "pre_resolve")
        self.resolve_payload()
        print(f"{'  ' * self.level}{self.typename} resolves")
        self.resolved = True
        self.engine.broadcast(self, "post_resolve")
        self.step_function = self.resolve_child

    def resolve_child(self):
        if self.list_children_queue:
            self.active_child = self.list_children_queue.pop(0)
            self.engine.active_action = self.active_child
            return

        self.end_of_children()
        if not self.list_children_queue:
            self.step_function = self.close

    def close(self):
        self.engine.active_action = self.parent
        if self.parent is not None:
            self.parent.list_children_done.append(self)
            self.parent.active_child = None
        self.closed = True
        self.step_function = None

    def add_child(self, action_type, battle=None, dotmap=None):
        """Queue an ``Action`` subclass, inheriting this action's battle by default."""
        child_battle = self.battle if battle is None else battle
        child_dotmap = DotMap() if dotmap is None else dotmap
        self.list_children_queue.append(action_type(self.engine, child_battle, self, child_dotmap))

    def root_action(self):
        """Return the root action that owns campaign-level state."""
        action = self
        while action.parent is not None:
            action = action.parent
        return action

    def post_init(self):
        pass

    def resolve_payload(self):
        pass

    def validate(self):
        return True

    def end_of_children(self):
        pass


class Battle:
    """State for one battle in the demonstration campaign."""

    def __init__(self):
        self.hero = None
        self.dummy = None
        self.hero_damage = 0
        self.round = 0
        self.done = False


class Character:
    """Mutable character state used by campaign and battle actions."""

    def __init__(self, name, hp_base, hp_current=None):
        self.name = name
        self.hp_base = hp_base
        self.hp_current = hp_base if hp_current is None else hp_current

    @classmethod
    def from_persistent(cls, character):
        """Build a battle-local character from campaign state."""
        return cls(character.name, character.hp_base, character.hp_current)


# Action implementations remain in this module and are registered below as
# Action.<ActionName>. Keeping the registration together makes Action the
# single public namespace without moving actions to another module.
class CampaignRoot(Action):
    def post_init(self):
        self.list_battles = []
        self.hero = None

    def resolve_payload(self):
        self.hero = Character("hero", hp_base=100)

    def end_of_children(self):
        if len(self.list_battles) < 3:
            battle = Battle()
            self.list_battles.append(battle)
            self.add_child(Action.BattleRoot, battle=battle)


class BattleRoot(Action):
    def resolve_payload(self):
        self.add_child(Action.BattleStart)
        self.add_child(Action.BattleLoop)
        self.add_child(Action.BattleEnd)


class BattleStart(Action):
    def resolve_payload(self):
        campaign_hero = self.root_action().hero
        self.battle.hero = Character.from_persistent(campaign_hero)
        self.battle.dummy = Character("dummy", hp_base=60)
        self.battle.hero_damage = 6
        self.battle.round = 0


class BattleLoop(Action):
    def end_of_children(self):
        if self.battle.dummy.hp_current > 0:
            self.add_child(Action.Round, dotmap=DotMap(round=self.battle.round))


class BattleEnd(Action):
    def resolve_payload(self):
        self.root_action().hero.hp_current = self.battle.hero.hp_current
        self.battle.done = True


class Round(Action):
    def resolve_payload(self):
        self.battle.round += 1
        self.add_child(Action.TurnHero)
        self.add_child(Action.TurnDummy)


class TurnHero(Action):
    def resolve_payload(self):
        self.add_child(
            Action.DamageSend,
            dotmap=DotMap(
                source=self.battle.hero,
                target=self.battle.dummy,
                damage=self.battle.hero_damage,
            ),
        )


class TurnDummy(Action):
    def resolve_payload(self):
        self.add_child(
            Action.DamageSend,
            dotmap=DotMap(source=self.battle.dummy, target=self.battle.hero, damage=1),
        )


class DamageSend(Action):
    def resolve_payload(self):
        self.add_child(Action.DamageReceive, dotmap=self.dotmap.copy())


class DamageReceive(Action):
    def resolve_payload(self):
        self.dotmap.target.hp_current -= self.dotmap.damage


class BlockGain(Action):
    def resolve_payload(self):
        pass


for _action_type in (
    CampaignRoot,
    BattleRoot,
    BattleStart,
    BattleLoop,
    BattleEnd,
    Round,
    TurnHero,
    TurnDummy,
    DamageSend,
    DamageReceive,
    BlockGain,
):
    setattr(Action, _action_type.__name__, _action_type)

del _action_type
del (
    CampaignRoot,
    BattleRoot,
    BattleStart,
    BattleLoop,
    BattleEnd,
    Round,
    TurnHero,
    TurnDummy,
    DamageSend,
    DamageReceive,
    BlockGain,
)


class Rule:
    """Listens to action-resolution broadcasts."""

    def __call__(self, action, timing):
        pass


class Engine:
    """The outermost shell of the game logic."""

    def __init__(self, steps_max=10**6):
        self.steps_max = steps_max
        self.steps_current = 0
        self.active_action = Action.CampaignRoot(self)
        self.nested_list_action_tree = [self.active_action]
        self.list_rules = []

    def broadcast(self, action, timing):
        for rule in self.list_rules:
            rule(action, timing)

    def run(self):
        while self.active_action is not None and self.steps_current < self.steps_max:
            self.steps_current += 1
            self.active_action.step()


class RuleVorpal(Rule):
    """Occasionally turn outgoing damage into a powerful hit."""

    def __call__(self, action, timing):
        if isinstance(action, Action.DamageSend) and timing == "pre_resolve":
            if random.randint(0, 2) == 2:
                action.dotmap.damage = 99


class RuleThorny(Rule):
    """Cause a target to retaliate after it receives damage."""

    def __init__(self, owner, amount):
        self.owner = owner
        self.amount = amount

    def __call__(self, action, timing):
        if (
            isinstance(action, Action.DamageReceive)
            and timing == "post_resolve"
            and action.dotmap.target.name == self.owner
        ):
            action.add_child(
                Action.DamageSend,
                dotmap=DotMap(
                    source=action.dotmap.target,
                    target=action.dotmap.source,
                    damage=self.amount,
                ),
            )


def build_demo_engine():
    engine = Engine()
    engine.list_rules.append(RuleVorpal())
    engine.list_rules.append(RuleThorny("dummy", 1))
    return engine


if __name__ == "__main__":
    build_demo_engine().run()
