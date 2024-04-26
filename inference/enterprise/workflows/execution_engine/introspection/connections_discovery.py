from collections import defaultdict
from typing import Dict, Set, Type

from inference.enterprise.workflows.entities.types import (
    STEP_AS_SELECTED_ELEMENT,
    STEP_OUTPUT_AS_SELECTED_ELEMENT,
    WILDCARD_KIND,
)
from inference.enterprise.workflows.execution_engine.introspection.entities import (
    BlockManifestMetadata,
    BlockPropertyDefinition,
    BlocksConnections,
    BlocksDescription,
    DiscoveredConnections,
)
from inference.enterprise.workflows.execution_engine.introspection.schema_parser import (
    parse_block_manifest_schema,
)
from inference.enterprise.workflows.prototypes.block import WorkflowBlock


def discover_blocks_connections(
    blocks_description: BlocksDescription,
) -> DiscoveredConnections:
    all_schemas = parse_all_schemas(blocks_description=blocks_description)
    output_kind2schemas = get_all_outputs_kind_major(
        blocks_description=blocks_description
    )
    detailed_input_kind2schemas = get_all_inputs_kind_major(
        blocks_description=blocks_description,
        all_schemas=all_schemas,
    )
    coarse_input_kind2schemas = convert_kinds_mapping_to_block_wise_format(
        detailed_input_kind2schemas=detailed_input_kind2schemas,
        compatible_elements={STEP_OUTPUT_AS_SELECTED_ELEMENT},
    )
    input_property_wise_connections = {}
    output_property_wise_connections = {}
    for manifest_type in all_schemas.keys():
        input_property_wise_connections[manifest_type] = (
            discover_block_input_connections(
                starting_block=manifest_type,
                all_schemas=all_schemas,
                output_kind2schemas=output_kind2schemas,
            )
        )
        output_property_wise_connections[manifest_type] = (
            discover_block_output_connections(
                starting_block=manifest_type,
                input_kind2schemas=coarse_input_kind2schemas,
            )
        )
    input_block_wise_connections = (
        convert_property_connections_to_block_wise_connections(
            property_wise_connections=input_property_wise_connections,
        )
    )
    output_block_wise_connections = (
        convert_property_connections_to_block_wise_connections(
            property_wise_connections=output_property_wise_connections,
        )
    )
    input_connections = BlocksConnections(
        property_wise=input_property_wise_connections,
        block_wise=input_block_wise_connections,
    )
    output_connections = BlocksConnections(
        property_wise=output_property_wise_connections,
        block_wise=output_block_wise_connections,
    )
    return DiscoveredConnections(
        input_connections=input_connections,
        output_connections=output_connections,
        kinds_connections=detailed_input_kind2schemas,
    )


def parse_all_schemas(
    blocks_description: BlocksDescription,
) -> Dict[Type[WorkflowBlock], BlockManifestMetadata]:
    return {
        block.block_class: parse_block_manifest_schema(schema=block.block_schema)
        for block in blocks_description.blocks
    }


def get_all_outputs_kind_major(
    blocks_description: BlocksDescription,
) -> Dict[str, Set[Type[WorkflowBlock]]]:
    kind_major_step_outputs = defaultdict(set)
    for block in blocks_description.blocks:
        kind_major_step_outputs[WILDCARD_KIND.name].add(block.block_class)
        for output in block.outputs_manifest:
            for kind in output.kind:
                kind_major_step_outputs[kind.name].add(block.block_class)
    return kind_major_step_outputs


def get_all_inputs_kind_major(
    blocks_description: BlocksDescription,
    all_schemas: Dict[Type[WorkflowBlock], BlockManifestMetadata],
) -> Dict[str, Set[BlockPropertyDefinition]]:
    kind_major_step_inputs = defaultdict(set)
    for block_description in blocks_description.blocks:
        for selector in all_schemas[block_description.block_class].selectors.values():
            for allowed_reference in selector.allowed_references:
                if allowed_reference.selected_element == STEP_AS_SELECTED_ELEMENT:
                    continue
                for single_kind in allowed_reference.kind:
                    kind_major_step_inputs[single_kind.name].add(
                        BlockPropertyDefinition(
                            block_type=block_description.block_class,
                            manifest_type_identifier=block_description.manifest_type_identifier,
                            property_name=selector.property_name,
                            compatible_element=allowed_reference.selected_element,
                        )
                    )
                kind_major_step_inputs[WILDCARD_KIND.name].add(
                    BlockPropertyDefinition(
                        block_type=block_description.block_class,
                        manifest_type_identifier=block_description.manifest_type_identifier,
                        property_name=selector.property_name,
                        compatible_element=allowed_reference.selected_element,
                    )
                )
    return kind_major_step_inputs


def discover_block_input_connections(
    starting_block: Type[WorkflowBlock],
    all_schemas: Dict[Type[WorkflowBlock], BlockManifestMetadata],
    output_kind2schemas: Dict[str, Set[Type[WorkflowBlock]]],
) -> Dict[str, Set[Type[WorkflowBlock]]]:
    result = {}
    for selector in all_schemas[starting_block].selectors.values():
        blocks_matching_property = set()
        for allowed_reference in selector.allowed_references:
            if allowed_reference.selected_element != STEP_OUTPUT_AS_SELECTED_ELEMENT:
                continue
            for single_kind in allowed_reference.kind:
                blocks_matching_property.update(
                    output_kind2schemas.get(single_kind.name, set())
                )
        result[selector.property_name] = blocks_matching_property
    return result


def discover_block_output_connections(
    starting_block: Type[WorkflowBlock],
    input_kind2schemas: Dict[str, Set[Type[WorkflowBlock]]],
) -> Dict[str, Set[Type[WorkflowBlock]]]:
    result = {}
    for output in starting_block.describe_outputs():
        compatible_blocks = set()
        for single_kind in output.kind:
            compatible_blocks.update(input_kind2schemas[single_kind.name])
        result[output.name] = compatible_blocks
    return result


def convert_property_connections_to_block_wise_connections(
    property_wise_connections: Dict[
        Type[WorkflowBlock], Dict[str, Set[Type[WorkflowBlock]]]
    ],
) -> Dict[Type[WorkflowBlock], Set[Type[WorkflowBlock]]]:
    result = {}
    for block_type, properties_connections in property_wise_connections.items():
        block_connections = set()
        for property_connections in properties_connections.values():
            block_connections.update(property_connections)
        result[block_type] = block_connections
    return result


def convert_kinds_mapping_to_block_wise_format(
    detailed_input_kind2schemas: Dict[str, Set[BlockPropertyDefinition]],
    compatible_elements: Set[str],
) -> Dict[str, Set[Type[WorkflowBlock]]]:
    result = defaultdict(set)
    for kind_name, block_properties_definitions in detailed_input_kind2schemas.items():
        for definition in block_properties_definitions:
            if definition.compatible_element not in compatible_elements:
                continue
            result[kind_name].add(definition.block_type)
    return result
