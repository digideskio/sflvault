#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
#    sflvault_qt/tree/tree.py
#
#    This file is part of SFLvault-QT
#
#    Copyright (C) 2009 Thibault Cohen
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#


import sys
from PyQt4 import QtCore, QtGui, QtWebKit

from sflvault.client import SFLvaultClient
from sflvault_qt.bar.filterbar import FilterBar
from sflvault_qt.dialog.webpreview import WebPreview
from images.qicons import *

from lib.auth import *


class TreeItem(QtCore.QObject):
    def __init__(self, data, icon=None, parent=None):
        self.parentItem = parent
        self.itemData = data
        self.childItems = []
        self.icon = icon

    def appendChild(self, item):
        self.childItems.append(item)

    def child(self, row):
        return self.childItems[row]

    def childCount(self):
        return len(self.childItems)

    def columnCount(self):
        return len(self.itemData)

    def data(self, column):
        return self.itemData[column]

    def parent(self):
        return self.parentItem

    def row(self):
        if self.parentItem:
            return self.parentItem.childItems.index(self)
        return 0


class TreeModel(QtCore.QAbstractItemModel):
    def __init__(self, research=None, groups_ids=None, parentView=None):
        QtCore.QAbstractItemModel.__init__(self, parentView)
        self.parentView = parentView

        rootData = []
        rootData.append(QtCore.QVariant("Name"))
        rootData.append(QtCore.QVariant("Id"))
        self.rootItem = TreeItem(rootData)
        self.research = research
        self.groups_ids = groups_ids

        # Init data item tree
        parents = []
        parents.append(self.rootItem)

        if not self.research:
            self.research = "."
        all = vaultSearch(self.research, self.groups_ids)

        for custoid, custo in all["results"].items():
            parents[-1].appendChild(TreeItem([custo["name"],"c#" + custoid], Qicons("customer"), parents[-1]))
            parents.append(parents[-1].child(parents[-1].childCount() - 1))

            for machineid, machine in custo["machines"].items():
                parents[-1].appendChild(TreeItem([machine["name"],"m#" + machineid], Qicons("machine"), parents[-1]))
                parents.append(parents[-1].child(parents[-1].childCount() - 1))

                for serviceid, service in machine["services"].items():
                    if not service["url"]:
                        continue
                    else:
                        protocol = service["url"].split(":")[0]
                        parents[-1].appendChild(TreeItem([service["url"],"s#" + serviceid], Qicons(protocol, "service"), parents[-1]))

                parents.pop()

            parents.pop()

    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.rootItem.columnCount()

    def data(self, index, role):
        if not index.isValid():
            return QtCore.QVariant()

        item = index.internalPointer()

        if role == QtCore.Qt.DecorationRole and index.column() == 0:
            return  QtCore.QVariant(item.icon)

        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()

        return QtCore.QVariant(item.data(index.column()))

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled

        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self.rootItem.data(section)

        return QtCore.QVariant()

    def index(self, row, column, parent):
        if row < 0 or column < 0 or row >= self.rowCount(parent) or column >= self.columnCount(parent):
            return QtCore.QModelIndex()

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QtCore.QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()

        childItem = index.internalPointer()
        parentItem = childItem.parent()

        if parentItem == self.rootItem:
            return QtCore.QModelIndex()

        if parentItem != None:
            return self.createIndex(parentItem.row(), 0, parentItem)
        else:
            return QtCore.QModelIndex()

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        return parentItem.childCount()

    def children(self, parent):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        return parentItem.childItems


class proxyVault(QtGui.QSortFilterProxyModel):
    def __init__(self, parent=None):
        QtGui.QSortFilterProxyModel.__init__(self, parent)
        self.setDynamicSortFilter(1)
        self.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.source_model = self.sourceModel()
        self.shown = set()
        self.match = set()

    def filterAcceptsRow(self, sourceRow, sourceParent):
        """
            Permit to filter on 2 first columns
        """
        self.source_model = self.sourceModel()
        # By name
        index_name = self.source_model.index(sourceRow,0,sourceParent)
        # By id
        index_id = self.source_model.index(sourceRow,1,sourceParent)
        # Get pattern
        pattern = unicode(self.filterRegExp().pattern())
    
        if unicode(index_id.data(0).toString()).find(pattern) != -1: 
            # Add it in shown list
            self.shown.add(index_name)
            # Add it in match list
            self.match.add(index_name)
            return True
        if unicode(index_name.data(0).toString()).find(pattern) != -1:
            # Add it in shown list
            self.shown.add(index_name)
            # Add it in match list
            self.match.add(index_name)
            return True

        # Check if parent is shown and show only if 
        # at least one of its children is going to be shown
        parent_index = self.source_model.parent(index_name)
        if parent_index in self.shown:
            # Show it if its parent match
            if parent_index in self.match:
                # Add it in shown list
                self.shown.add(index_name)
                # remove it in match list if exist in
                if index_name in self.match:
                    self.match.remove(index_name)               
                return True
            # Show it if its granpa match
            if self.source_model.parent(parent_index) in self.match:
                # Add it in shown list
                self.shown.add(index_name)
                # remove it in match list if exist in
                if index_name in self.match:
                    self.match.remove(index_name)
                return True

        # Show it if one a its child match
        for child in self.source_model.children(index_name):
            if unicode(child.data(0)).find(pattern) != -1 or unicode(child.data(1)).find(pattern) != -1:
                # Add it in shown list
                self.shown.add(index_name)
                # remove it in match list if exist in
                if index_name in self.match:
                    self.match.remove(index_name)
                return True
            # Show it if one a its little child match
            for subchild in child.childItems:
                if unicode(subchild.data(0)).find(pattern) != -1 or unicode(subchild.data(1)).find(pattern) != -1 :
                    # Add it in shown list
                    self.shown.add(index_name)
                    # remove it in match list if exist in
                    if index_name in self.match:
                        self.match.remove(index_name)
                    return True

        # remove index_name if it s in shown list
        if index_name in self.shown:
            self.shown.remove(index_name)
        # remove it in match list if exist in
        if index_name in self.match:
            self.match.remove(index_name)
        return False


class TreeView(QtGui.QTreeView):
    def __init__(self, parent=None):
        QtGui.QTreeView.__init__(self, parent)
        self.parent = parent
        # Load proxy
        self.proxyModel = proxyVault(self)
        # Set view properties
        self.setSortingEnabled(1)
        self.setModel(self.proxyModel)
        self.sortByColumn(0,QtCore.Qt.AscendingOrder)
        # Load context actions
        self.createActions()
        
        self.setMouseTracking(1)
        self.connect(self,QtCore.SIGNAL("entered (const QModelIndex&)"), self.webPreview)

    def webPreview(self, index):
        url = QtCore.QUrl(index.data().toString())
        if url.scheme().startsWith("http"):
          #  self.webpreview = QtWebKit.QWebView(self)
          #  self.webpreview.load(url)
          #  self.webpreview.show()
            web = WebPreview(url,self)
#            web.load(url)
#            scene = QtGui.QGraphicsScene()
#            scene.addItem(web)
#            scene.addText("Hello, world!")
#            view = QtGui.QGraphicsView(scene)
            web.show()
#            web.setPos(200,200)
#            web.scene()

#            view.show()
            print str(url.scheme())
            print url


    def setGeometries(self):
        """
            Set headers size
        """
        h = self.header()
        h.setResizeMode(0, QtGui.QHeaderView.Stretch)
        h.setStretchLastSection(0)
        self.setColumnWidth(1,65)

    def search(self, research, groups_ids=None):
        # Get minimum number of caracters to search
        minsearch = self.parent.settings.value("SFLvault-qt4/minsearch").toInt()[0]
        # Test if research if not null or if it contains just empty unicode
        if research and not research == [u'']:
            # Join all research words
            research_length = len("".join(research))
            # If not null, test if the length if < minsearch
            if research_length < minsearch:
                # If yes, do nothing
                return None
        # Load model
        self.sourcemodel = TreeModel(research, groups_ids, self)
        # Load proxy
        self.proxyModel.setSourceModel(self.sourcemodel)
        if research and not research == [u''] :
            self.expandAll()
        else:
            self.collapseAll()
        # Sort by name
        self.sortByColumn(0)

    def contextMenuEvent(self, event):
        """
            Create contextMenu on right click
        """
        if self.selectedIndexes():
            menu = QtGui.QMenu(self)
            # Add bookmark menu for services
            if self.selectedIndexes()[0].parent().parent().isValid():
                menu.addAction(self.bookmarkAct)
            menu.addAction(self.editAct)
            menu.addAction(self.delAct)
            menu.exec_(event.globalPos())

    def createActions(self):
        """
            Create actions for contextMenu
        """
        self.editAct = QtGui.QAction(self.tr("&Edit..."), self)
        self.editAct.setShortcut(self.tr("Ctrl+E"))
        self.editAct.setStatusTip(self.tr("Edit item"))

        self.bookmarkAct = QtGui.QAction(self.tr("&Create alias..."), self)
        self.bookmarkAct.setShortcut(self.tr("Ctrl+D"))
        self.bookmarkAct.setStatusTip(self.tr("Create an alias from this item"))

        self.delAct = QtGui.QAction(self.tr("&Delete..."), self)
        self.delAct.setStatusTip(self.tr("Delete item"))

    def filter(self, pattern):
        """
            Filter and expand
        """
        self.proxyModel.setFilterRegExp(pattern)
        self.expandAll()
        # Sort by name
        self.sortByColumn(0)
        
    def expandCollapse(self):
        """
            Expand or collapse selected item
        """
        indexes = self.selectedIndexes()
        # Check if an item if selected
        if indexes:
            # Check if is a node
            if indexes[0].child(0,0).isValid():
                if self.isExpanded(indexes[0]):
                    self.collapse(indexes[0])
                else:
                    self.expand(indexes[0])

    def enterShortcut(self):
        """
            Expand-collapse if selected item is a customer/machine
            Launch connection if service
        """
        indexes = self.selectedIndexes()
        # Check if an item if selected
        if indexes:
            # if item is a service
            if indexes[0].parent().parent().isValid():
                self.parent.GetIdByTree(indexes[0])
            # if item is a customer or machine
            else:
                self.expandCollapse()

class TreeVault(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.parent = parent

        self.tree = TreeView(parent)
        self.filter = FilterBar(self) 
        self.filter.connect(self.filter.filter_input, QtCore.SIGNAL("textChanged(const QString&)"), self.tree.filter)

        layout = QtGui.QVBoxLayout(self);
        layout.setSpacing(0)
        layout.setMargin(0)

        layout.addWidget(self.tree)
        layout.addWidget(self.filter)
        self.setShortcut()

    def connection(self):
        self.tree.search(None, None)
        self.tree.setGeometries()

    def setShortcut(self):
        """
            Define tree shortcuts
        """
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space),
                self.tree, self.tree.expandCollapse, None, QtCore.Qt.WidgetShortcut)
        # FIXME Disable cause QtCore.Qt.WidgetShortcut context doesn t work
#        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return),
#                self.tree, self.tree.enterShortcut, None, QtCore.Qt.WidgetShortcut)
