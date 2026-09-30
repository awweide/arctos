import uuid
import random
from dotmap import DotMap


#Actions namespace is broken; Actions are direclty exposed, not in Actions.xyz
class Action:
    def __init__(self, engine, battle, parent, dotmap):
        self.id = str(uuid.uuid4())

        self.engine = engine
        self.battle = battle
        self.parent = parent
        self.list_children_queue = []
        self.list_children_done = []
        self.active_child = None
        self.step_function = self.resolve
        self.dotmap = dotmap

        self.resolved = False
        self.closed = False

        self.level = 0 if parent == None else parent.level + 1
        self.typename = type(self).__name__
        self.post_init()
        
    #DO NOT OVERRIDE
    def step(self): self.step_function()
                
    def resolve(self):
        if self.validate():
            self.engine.broadcast(self, "pre_resolve")
            self.resolve_payload()
            print(f"{'  ' * self.level}{self.typename} resolves")
            self.resolved = True
            self.engine.broadcast(self, "post_resolve")
            self.step_function = self.resolve_child
        else:
            print(f"{'  ' * self.level}{self.typename} invalid")
            self.step_function = self.close
            
    def resolve_child(self):
        if self.list_children_queue:
            self.active_child = self.list_children_queue.pop(0)
            self.engine.active_action = self.active_child
        else:
            self.end_of_children()
            if not self.list_children_queue:
                self.step_function = self.close
                
    def close(self):
        self.engine.active_action = self.parent
        if self.parent:
            self.parent.list_children_done.append(self)
            self.parent.active_child = None
        self.closed = True
        self.step_function = None

    def add_child(self, action_type, battle = None, dotmap = None):
        self.list_children_queue.append(action_type(self.engine, battle if battle else self.battle, self, dotmap if dotmap else DotMap()))

    #DO OVERRIDE
    def post_init(self): pass
    
    def resolve_payload(self): pass
        
    def validate(self):
        #Check if Action is compatible with current state, for instance
        #if not self.source.alive or not self.target.alive: return False
        return True
    
    def end_of_children(self):
        #For looping behavior:
        #if conditional: self.list_children_queue.append(Action(sefl.engine, self.battle, self))
        pass

        
        
#--------
class Battle:
    def __init__(self):
        self.dummy_hp = 0
        self.hero_damage = 0
        self.round = 0
        self.done = False

class CampaignRoot(Action):
    def post_init(self):
        self.list_battles = []
        
    def end_of_children(self):
        if len(self.list_battles) < 3:
            battle = Battle()
            self.list_battles.append(battle)
            self.add_child(BattleRoot, battle)

class BattleRoot(Action):
    def resolve_payload(self):
        self.add_child(BattleStart)
        self.add_child(BattleLoop)
        self.add_child(BattleEnd)
        
class BattleStart(Action):
    def resolve_payload(self):
        self.battle.dummy_hp = 60
        self.battle.hero_damage = 6
        self.battle.round = 0

class BattleLoop(Action):
    def end_of_children(self):
        if self.battle.dummy_hp > 0:
            self.add_child(Round, dotmap = DotMap({"round" : self.battle.round}))

class BattleEnd(Action):
    def resolve_payload(self):
        self.battle.done = True

class Round(Action):
    def resolve_payload(self):
        self.add_child(TurnHero)
        self.add_child(TurnDummy)

class TurnHero(Action):
    def resolve_payload(self):
        self.add_child(DamageSend, dotmap = DotMap({"source" : "hero", "target" : "dummy", "damage" : self.battle.hero_damage}))
        
class TurnDummy(Action):
    def resolve_payload(self):
        self.battle.dummy_hp += 1
        
class DamageSend(Action):
    def resolve_payload(self):
        self.add_child(DamageReceive)

class DamageReceive(Action):
    def resolve_payload(self):
        self.battle.dummy_hp -= self.dotmap.damage

class BlockGain(Action):
    def resolve_payload(self):
        pass

#All reactive logic is handled by rules -- listens to and reacts to "broadcasts"
class Rule:
    def __init__(self): pass
    def __call__(self, action, timing): pass

#The outermost shell of the game logic
class Engine:
    def __init__(self):
        self.steps_max = 10**6
        self.steps_current = 0
        self.active_action = Actions.CampaignRoot(self, Nonet, None, DotMap())
        self.nested_list_action_tree = [self.active_action]
        
        self.hero = Hero(hp_base = 100)
        
        self.list_rules = []

    def broadcast(self, action, timing):
        for rule in self.list_rules:
            rule(action, timing)

    def run(self):
        while self.active_action != None and self.steps_current < self.steps_max:
            self.steps_current += 1
            self.active_action.step()

#Tester rule, mutates at interrupt timing
class RuleVorpal(Rule):
    def __call__(self, action, timing):
        if isinstance(action, Actions.DamageSend) and timing == "pre_resolve":
            if random.randint(0,2) == 2:
                action.dotmap.damage = 99

#Tester rule, triggers at react timing
class RuleThorny(Rule):
    def __init__(self, owner, amount):
        self.owner = owner
        self.amount = amount
        
    def __call__(self, action, timing):
        if isinstance(action, Actions.DamageReceive) and timing == "post_resolve" and action.dotmap.target == self.owner:
            action.add_child(Actions.DamageSend, DotMap({"source" : action.dotmap.target, "target" : action.dotmap.source, "damage" : self.amount}))

#Holds all Battle-specific state
class Battle:
    def __init__(self, hero, monster, ix_round):
        self.hero = hero
        self.monster = monster
        self.ix_round = ix_round
        self.done = False

#Superclass for player-avatar and enemy objects
class Character:
    def __init__(self, name, hp_base):
        self.name = name
        self.hp_base = hp_base
        self.hp_current = hp_base
        self.block = 0
        self.post_init()
        
    def post_init(self): pass

    def get_action_turn(self, action_parent):
        raise ValueError
    
class Hero(Character):
    def get_action_turn(self, action_parent):
        pass

class SimpleMonster(Character):
    def get_action_turn(self, action_parent):
        action_parent.add_child(Actions.DamageSend, DotMap({"source":self, "target":"", "damage":5}))
        action_parent.add_child(Actions.BlockGain, DotMap({"source":self, "target":self, "block":5})

engine = Engine()
engine.list_rules.append(RuleVorpal())
engine.list_rules.append(RuleThorny("dummy", 1))
engine.run()
