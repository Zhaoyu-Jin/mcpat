"""
[usage]:
python3 Gem5ToMcPAT-Parser.py -c ../m5out/config.json -s ../m5out/stats.txt -t template.xml
python3 Gem5McPATParser_custom.py -c ./test_config_stats/config.json -s ./test_config_stats/stats.txt -t ./templates/template_x86.xml

# Tested
python 3.6.9
python 3.8.5

"""

"""
Modified from https://github.com/saideeptiku/Gem5McPatParser to fit our
gem5 output format
"""

import argparse
import sys
import json
import re
from xml.etree import ElementTree as ET
from xml.dom import minidom
import copy
import types
import logging


def prettify(elem):
    """Return a pretty-printed XML string for the Element.
    """
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def create_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Gem5 to McPAT parser")

    parser.add_argument(
        '--config', '-c', type=str, required=True,
        metavar='PATH',
        help="Input config.json from Gem5 output.")
    parser.add_argument(
        '--stats', '-s', type=str, required=True,
        metavar='PATH',
        help="Input stats.txt from Gem5 output.")
    parser.add_argument(
        '--template', '-t', type=str, required=True,
        metavar='PATH',
        help="Template XML file")
    parser.add_argument(
        '--output', '-o', type=argparse.FileType('w'), default="mcpat-in.xml",
        metavar='PATH',
        help="Output file for McPAT input in XML format (default: mcpat-in.xml)")

    return parser


class PIParser(ET.TreeBuilder):
    def __init__(self, *args, **kwargs):
        # call init of superclass and pass args and kwargs
        super(PIParser, self).__init__(*args, **kwargs)

        self.CommentHandler = self.comment
        self.ProcessingInstructionHandler = self.pi
        self.start("document", {})

    def close(self):
        self.end("document")
        return ET.TreeBuilder.close(self)

    def comment(self, data):
        self.start(ET.Comment, {})
        self.data(data)
        self.end(ET.Comment)

    def pi(self, target, data):
        self.start(ET.PI, {})
        self.data(target + " " + data)
        self.end(ET.PI)


def parse(source):
    parser = ET.XMLParser(target=PIParser())
    return ET.parse(source, parser=parser)


def readStatsFile(statsFile):
    global stats
    stats = {}
    F = open(statsFile)
    ignores = re.compile(r'^---|^$')
    statLine = re.compile(
        r'([a-zA-Z0-9_\.:-]+)\s+([-+]?[0-9]+\.[0-9]+|[-+]?[0-9]+|nan|inf)')
    count = 0
    for line in F:
        # ignore empty lines and lines starting with "---"
        if not ignores.match(line):
            count += 1
            statLine_match = statLine.match(line)
            if(statLine_match == None):
                print(f"Failed to match line: {line}")
                #assert(False)
            else:
                statKind = statLine.match(line).group(1)
                statValue = statLine.match(line).group(2)

            if statValue == 'nan':
                logging.warning("%s is nan. Setting it to 0" % statKind)
                statValue = '0'
            stats[statKind] = statValue
    F.close()


def readConfigFile(configFile):
    global config
    F = open(configFile)
    config = json.load(F)
    config["system"] = config.pop("board")
    # print config
    # print config["system"]["membus"]
    # print config["system"]["processor"]["o3"][0]["clock"]
    F.close()


def readMcpatFile(templateFile):
    global templateMcpat
    templateMcpat = parse(templateFile)
    # ET.dump(templateMcpat)


def prepareTemplate(outputFile):
    numCores = len(config["system"]["processor"]["o3"])
    privateL2 = True #'l2caches' in config["system"]["processor"]["o3"][0].keys()
    sharedL2 = False #'l2' in config["system"].keys()

    if privateL2:
        numL2 = numCores
    elif sharedL2:
        numL2 = 1
    else:
        numL2 = 0
    elemCounter = 0
    root = templateMcpat.getroot()
    print(f"template McPAT root[0] {root[0].get('name')} name root[0][0] name {root[0][0].get('name')}")
    # root 0 is the root, root[0][0] is the system element
    # child is each element in the system element
    for child in root[0][0]:
        # print(f"child attribute name {child.get('name')}")
        elemCounter += 1  # to add elements in correct sequence

        if child.attrib.get("name") == "number_of_cores":
            child.attrib['value'] = str(numCores)
        if child.attrib.get("name") == "number_of_L2s":
            child.attrib['value'] = str(numL2)
        if child.attrib.get("name") == "Private_L2":
            if sharedL2:
                Private_L2 = str(0)
            else:
                Private_L2 = str(1)
            child.attrib['value'] = Private_L2
        temp = child.attrib.get('value')

        # to consider all the cpus in total cycle calculation
        if isinstance(temp, str) and "cpu." in temp and temp.split('.')[0] == "stats":
            value = "(" + temp.replace("cpu.", "cpu0.") + ")"
            for i in range(1, numCores):
                value = value + \
                    " + (" + temp.replace("cpu.", "cpu"+str(i)+".") + ")"
            child.attrib['value'] = value

        # remove a core template element and replace it with number of cores template elements
        if child.attrib.get("name") == "core":
            coreElem = copy.deepcopy(child)
            coreElemCopy = copy.deepcopy(coreElem)
            for coreCounter in range(numCores):
                coreElem.attrib["name"] = "core" + str(coreCounter)
                coreElem.attrib["id"] = "system.core" + str(coreCounter)
                for coreChild in coreElem:
                    childId = coreChild.attrib.get("id")
                    childValue = coreChild.attrib.get("value")
                    childName = coreChild.attrib.get("name")
                    if isinstance(childName, str) and childName == "x86":
                        if config["system"]["processor"]["o3"][coreCounter]["core"]["isa"][0]["type"] == "X86ISA":
                            childValue = "1"
                        else:
                            childValue = "0"
                    if isinstance(childId, str) and "core" in childId:
                        childId = childId.replace(
                            "core", "core" + str(coreCounter))
                    if isinstance(childValue, str) and "cpu." in childValue and "stats" in childValue.split('.')[0]:
                        childValue = childValue.replace(
                            "cpu.", "cpu" + str(coreCounter) + ".")
                    if isinstance(childValue, str) and "cpu." in childValue and "config" in childValue.split('.')[0]:
                        childValue = childValue.replace(
                            "cpu.", "cpu." + str(coreCounter) + ".")
                    if len(list(coreChild)) != 0:
                        for level2Child in coreChild:
                            level2ChildValue = level2Child.attrib.get("value")
                            if isinstance(level2ChildValue, str) and "cpu." in level2ChildValue and "stats" in level2ChildValue.split('.')[0]:
                                level2ChildValue = level2ChildValue.replace(
                                    "cpu.", "cpu" + str(coreCounter) + ".")
                            if isinstance(level2ChildValue, str) and "cpu." in level2ChildValue and "config" in level2ChildValue.split('.')[0]:
                                level2ChildValue = level2ChildValue.replace(
                                    "cpu.", "cpu." + str(coreCounter) + ".")
                            level2Child.attrib["value"] = level2ChildValue
                    if isinstance(childId, str):
                        coreChild.attrib["id"] = childId
                    if isinstance(childValue, str):
                        coreChild.attrib["value"] = childValue
                root[0][0].insert(elemCounter, coreElem)
                coreElem = copy.deepcopy(coreElemCopy)
                elemCounter += 1
            root[0][0].remove(child)
            elemCounter -= 1

        # # remove a L2 template element and replace it with the private L2 template elements
        # if child.attrib.get("name") == "L2.shared":
        #     print child
        #     if sharedL2:
        #         child.attrib["name"] = "L20"
        #         child.attrib["id"] = "system.L20"
        #     else:
        #         root[0][0].remove(child)

        # remove a L2 template element and replace it with number of L2 template elements
        if child.attrib.get("name") == "L2":
            if privateL2:
                l2Elem = copy.deepcopy(child)
                l2ElemCopy = copy.deepcopy(l2Elem)
                for l2Counter in range(numL2):
                    l2Elem.attrib["name"] = "L2" + str(l2Counter)
                    l2Elem.attrib["id"] = "system.L2" + str(l2Counter)
                    for l2Child in l2Elem:
                        childValue = l2Child.attrib.get("value")
                        if isinstance(childValue, str) and "cpu." in childValue and "stats" in childValue.split('.')[0]:
                            childValue = childValue.replace(
                                "cpu.", "cpu" + str(l2Counter) + ".")
                        if isinstance(childValue, str) and "cpu." in childValue and "config" in childValue.split('.')[0]:
                            childValue = childValue.replace(
                                "cpu.", "cpu." + str(l2Counter) + ".")
                        if isinstance(childValue, str):
                            l2Child.attrib["value"] = childValue
                    root[0][0].insert(elemCounter, l2Elem)
                    l2Elem = copy.deepcopy(l2ElemCopy)
                    elemCounter += 1
                root[0][0].remove(child)
            else:
                child.attrib["name"] = "L20"
                child.attrib["id"] = "system.L20"
                for l2Child in child:
                    childValue = l2Child.attrib.get("value")
                    if isinstance(childValue, str) and "cpu.l2cache." in childValue:
                        childValue = childValue.replace("cpu.l2cache.", "l2.")

    prettify(root)
    # templateMcpat.write(outputFile)


def getConfValue(confStr):
    spltConf = re.split('\.', confStr)
    currConf = config
    currHierarchy = ""
    print(f"Extracting {spltConf} from Gem 5 Config.json")
    #print(currConf)

    for x in spltConf:
        currHierarchy += x
        if not x.isdigit():
            if (x not in currConf):
                print(f"{x} not found in GEM5 config.json")
                assert(False)
        
        if x.isdigit():
            #print(currConf[int(x)])
            currConf = currConf[int(x)]
        elif x in currConf:
            # if isinstance(currConf, types.ListType):
            #     #this is mostly for system.cpu* as system.cpu is an array
            #     #This could be made better
            #     if x not in currConf[0]:
            #         print "%s does not exist in config" % currHierarchy
            #     else:
            #         currConf = currConf[0][x]
            # else:
            #         print "***WARNING: %s does not exist in config.***" % currHierarchy
            #         print "\t Please use the right config param in your McPAT template file"
            # else:
            #print(currConf[x])
            currConf = currConf[x]
        currHierarchy += "."

    logging.info(confStr, currConf)

    return currConf

def adjust_stats_expression(template_expression):
    template_expression = re.sub('system.cpu\d?.', 'board.processor.o3.core.', template_expression)
    # TODO: didn't find systemCalls
    # TODO: BTB sizes?
    # TODO: memory controller stats were commented out for now

    # rename related
    if 'rename' in template_expression:
        template_expression = re.sub('rename.int_rename_lookups', 'rename.intLookups', template_expression) # look int reg rename
        template_expression = re.sub('rename.fp_rename_lookups', 'rename.fpLookups', template_expression)
        # TODO:(Done) update McPAT template so that rename_writes = rename.RenamedOperands_int; fp_rename_writes = rename.RenamedOperands_fp
    
    # IQ related
    if 'iq' in template_expression:
        template_expression = re.sub('iq.FU_type_0', 'statIssuedInstType_0', template_expression)
        template_expression = re.sub('iq.iqInstsIssued', 'instsIssued', template_expression)
        template_expression = re.sub('iq.int_inst_queue_reads', 'intInstQueueReads', template_expression)
        template_expression = re.sub('iq.int_inst_queue_writes', 'intInstQueueWrites', template_expression)
        template_expression = re.sub('iq.int_inst_queue_wakeup_accesses', 'intInstQueueWakeupAccesses', template_expression)
        template_expression = re.sub('iq.fp_inst_queue_reads', 'fpInstQueueReads', template_expression)
        template_expression = re.sub('iq.fp_inst_queue_writes', 'fpInstQueueWrites', template_expression)
        template_expression = re.sub('iq.fp_inst_queue_wakeup_accesses', 'fpInstQueueWakeupAccesses', template_expression)
        template_expression = re.sub('iq.int_alu_accesses', 'intAluAccesses', template_expression)
        template_expression = re.sub('iq.fp_alu_accesses', 'fpAluAccesses', template_expression)

    # Register file related
    if 'regfile' in template_expression:
        template_expression = re.sub('int_regfile_reads', 'intRegfileReads', template_expression)
        template_expression = re.sub('int_regfile_writes', 'intRegfileWrites', template_expression)
        template_expression = re.sub('fp_regfile_reads', 'fpRegfileReads', template_expression)
        template_expression = re.sub('fp_regfile_writes', 'fpRegfileWrites', template_expression)

    # itb/dtb
    # if 'itb' in template_expression:
        # Directly updated the template instead of here
        # # total itb accesses
        # template_expression = 'int(board.processor.o3.core.mmu.itb.rdAccesses + board.processor.o3.core.mmu.itb.wrAccesses)'
        # # total itb misses
        # template_expression = 'int(board.processor.o3.core.mmu.itb.rdMisses + board.processor.o3.core.mmu.itb.wrMisses)'
    
    # caches
    if 'icache' in template_expression:
        template_expression = re.sub('board.processor.o3.core.', 'board.', template_expression)
        template_expression = re.sub('icache.ReadReq_accesses::total', 'cache_hierarchy.l1icaches.ReadReq.accesses::total', template_expression)
        template_expression = re.sub('icache.ReadReq_misses::total', 'cache_hierarchy.l1icaches.ReadReq.misses::total', template_expression)
        template_expression = re.sub('icache.replacements', 'cache_hierarchy.l1icaches.replacements', template_expression)
    
    if 'dcache' in template_expression:
        template_expression = re.sub('board.processor.o3.core.', 'board.', template_expression)
        template_expression = re.sub('dcache.ReadReq_accesses::total', 'cache_hierarchy.l1dcaches.ReadReq.accesses::total', template_expression)
        template_expression = re.sub('dcache.ReadReq_misses::total', 'cache_hierarchy.l1dcaches.ReadReq.misses::total', template_expression)
        
        template_expression = re.sub('dcache.WriteReq_accesses::total', 'cache_hierarchy.l1dcaches.WriteReq.accesses::total', template_expression)
        template_expression = re.sub('dcache.WriteReq_misses::total', 'cache_hierarchy.l1dcaches.WriteReq.misses::total', template_expression)
        
        template_expression = re.sub('dcache.replacements', 'cache_hierarchy.l1dcaches.replacements', template_expression)

    # L2
    # TODO: directly updated the template, need to double check those updates are correct
    # <stat name="read_accesses" value="board.cache_hierarchy.l2caches.ReadSharedReq.accesses::total"/>
    # <stat name="write_accesses" value="board.cache_hierarchy.l2caches.ReadExReq.accesses::total"/>
    # <stat name="read_misses" value="board.cache_hierarchy.l2caches.ReadSharedReq.misses::total"/>
    # <stat name="write_misses" value="board.cache_hierarchy.l2caches.ReadExReq.misses::total"/>
        

    # rob related
    if 'rob' in template_expression:
        template_expression = re.sub('rob.rob_reads', 'rob.reads', template_expression)
        template_expression = re.sub('rob.rob_writes', 'rob.writes', template_expression)

    # commit related
    if 'commit' in template_expression:
        template_expression = re.sub('commit.committedOps', 'committedOps', template_expression) # total number of committed op
        template_expression = re.sub('commit.int_insts', 'commit.integer', template_expression)
        template_expression = re.sub('commit.fp_insts', 'commit.floating', template_expression)
        template_expression = re.sub('commit.function_calls', 'commit.functionCalls', template_expression)
    

    return template_expression

def dumpMcpatOut(outFile):
    """
    outfile: file reference to "mcpat-in.xml"
    """

    rootElem = templateMcpat.getroot()
    configMatch = re.compile(r'config\.([][a-zA-Z0-9_:\.]+)')
    # in the template o3 XML file, all params element that need to be filled
    # with info from gem5 config file has a value attribue with a temp value
    # that temp value has a patern that it will contain the word config
    # replace params with values from the GEM5 config file

    for param in rootElem.iter('param'):
        name = param.attrib['name']
        value = param.attrib['value']
    
        # if there is a config in this attrib
        if 'config' in value:
            print(f"\nMcPAT Requires {value}")
            # if this params need to get its value from gem5 config
            allConfs = configMatch.findall(value)
            # allconfs is the configuration name we are looking for in 
            # gem5's config file
            # print(allConfs)

            for conf in allConfs:
                # print(conf)
                confValue = getConfValue(conf)
                value = re.sub("config." + conf, str(confValue), value)
                #print(f"value extracted from gem5 config file {value}")

            if "," in value:
                exprs = re.split(',', value)
                for i in range(len(exprs)):
                    try:
                        exprs[i] = str(eval(exprs[i]))
                    except Exception as e:
                        logging.error("Possibly " + conf + " does not exist in config" +
                                      "\n\t set correct key string in template value")
                        raise

                param.attrib['value'] = ','.join(exprs)
            else:
                param.attrib['value'] = str(eval(str(value)))

    # replace stats with values from the GEM5 stats file
    statRe = re.compile(r'stats\.([a-zA-Z0-9_:\.]+)')
    # iterate through all stats element
    for stat in rootElem.iter('stat'):
        name = stat.attrib['name']
        # value is the stats expression defined in 
        # McPAT input template (template_x86.xml in our case)
        value = stat.attrib['value']

        # if we need to get this stats from gem5 stats
        if 'stats' in value:
            allStats = statRe.findall(value)
            print(f"McPAT requires {allStats} from Gem5 stats.txt for {name}")
            # each element in allStats is a stats we want to
            # find in GEM5's stats.txt
            expr = value
            for i in range(len(allStats)):
                # print(allStats[i])
                # need to adjust the allStats to fit our
                # GEM5 stats.txt pattern
                old_stats_i = allStats[i]
                allStats[i] = adjust_stats_expression(allStats[i])
                
                print(f"Extracting {allStats[i]} from Gem5 stats.txt")

                if allStats[i] in stats: # stats is an dictionary, key is the stats name in GEM5

                    expr = re.sub('stats.%s' %
                                  old_stats_i, stats[allStats[i]], expr)
                elif ".cpu0." in allStats[i]:
                    try:
                        cpu_stat = allStats[i].replace(".cpu0.", ".cpu.")
                        expr = re.sub('stats.%s' %
                                      old_stats_i, stats[cpu_stat], expr)
                    except KeyError:
                        logging.warning(allStats[i] +
                                        " does not exist in stats" +
                                        "\n\t Maybe invalid stat in McPAT template file")
                else:
                    # expr = re.sub('stats.%s' % allStats[i], str(1), expr)
                    logging.warning(allStats[i] +
                                    " does not exist in stats" +
                                    "\n\t Maybe invalid stat in McPAT template file or maybe it is zero. Setting it to zero")
                    expr = '0'
                    #assert(False)

            #print(f"write {expr}")
            if 'config' not in expr and 'stats' not in expr:
                stat.attrib['value'] = str(eval(expr))

    # Write out the xml file
    templateMcpat.write(outFile.name)


def main():
    global args
    parser = create_parser()
    args = parser.parse_args()
    readStatsFile(args.stats)
    #print(stats)
    readConfigFile(args.config)
    readMcpatFile(args.template)

    prepareTemplate(args.output)

    dumpMcpatOut(args.output)


if __name__ == '__main__':
    main()
